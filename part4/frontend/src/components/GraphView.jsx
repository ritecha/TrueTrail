import { useEffect, useMemo, useRef, useState, useCallback } from "react";
import ForceGraph2D from "react-force-graph-2d";
import {
  buildGraph,
  viewGraph,
  viewEngine,
  ROLE,
  KIND_COLOR,
} from "../graphLogic.js";

// ============================================================
// Configurable Google-Maps-Style 2D LOD Thresholds & Hysteresis
// Larger k = closer zoom
// ============================================================
export const LOD_CONFIG = {
  L2_ENTER: 1.15, // Overview -> Exploration
  L2_EXIT: 0.95, // Hysteresis prevents flicker
  L3_ENTER: 2.35, // Exploration -> Deep Zoom
  L3_EXIT: 2.05, // Hysteresis prevents flicker
  MIN_ZOOM: 0.25,
  MAX_ZOOM: 8,
  MAX_LABELS_L2: 36, // Cap floating labels in Level 2
};

const inr = (n) => "₹" + Math.round(n || 0).toLocaleString("en-IN");

function getReasons(n) {
  if (Array.isArray(n.reasons) && n.reasons.length > 0) return n.reasons;
  const out = [];
  if (n.role === "mule") {
    out.push(
      `High pass-through (${Math.round((n.passthrough || 0) * 100)}% forwarded)`,
    );
  } else if (n.role === "victim") {
    out.push("Primary source of outgoing funds in chain");
  } else if (n.role === "cashout") {
    out.push("Terminal account with minimal outflow");
  } else if (n.role === "handler") {
    out.push(`Called ${n.called || 0} flagged accounts after deposits`);
  }
  if ((n.devices?.size || 0) > 1) {
    out.push(`Shared across ${n.devices.size} devices`);
  }
  return out;
}

// Derive real schema rows from actual node attributes (no fake columns)
function getSchemaFields(n) {
  const shortId = String(n.id || "").slice(0, 14);
  if (n.role === "engine") {
    return [
      { key: "PK", name: "entity_id", type: shortId },
      { key: "", name: "kind", type: String(n.type || n.kind || "ENTITY") },
      ...(n.amount != null
        ? [{ key: "", name: "amount", type: inr(n.amount) }]
        : []),
      ...(n.source_file
        ? [
            {
              key: "FK",
              name: "source",
              type: String(n.source_file).slice(0, 14),
            },
          ]
        : []),
      ...(n.ctrl != null
        ? [{ key: "FK", name: "ctrl_score", type: Number(n.ctrl).toFixed(2) }]
        : []),
    ];
  }
  return [
    { key: "PK", name: "account_id", type: shortId },
    { key: "", name: "role", type: ROLE[n.role]?.label || n.role },
    { key: "", name: "in_flow", type: inr(n.inSum) },
    { key: "", name: "out_flow", type: inr(n.outSum) },
    {
      key: "FK",
      name: "passthrough",
      type: `${Math.round((n.passthrough || 0) * 100)}%`,
    },
    ...(n.devices?.size
      ? [{ key: "FK", name: "devices", type: `${n.devices.size} linked` }]
      : []),
    ...(n.ips?.size
      ? [{ key: "FK", name: "ip_addrs", type: `${n.ips.size} linked` }]
      : []),
  ];
}

function drawRoundedRect(ctx, x, y, w, h, r) {
  ctx.beginPath();
  ctx.roundRect(x, y, w, h, r);
}

export default function GraphView({
  transactions = [],
  calls = [],
  scores = {},
  engine,
  loading = false,
  error = null,
  onRetry,
}) {
  const graph = useMemo(
    () => buildGraph(transactions, calls, scores),
    [transactions, calls, scores],
  );
  const [mode, setMode] = useState("network");
  const [roleFilter, setRoleFilter] = useState("all");
  const [selected, setSelected] = useState(null);
  const [hovered, setHovered] = useState(null);
  const [q, setQ] = useState("");
  const [miss, setMiss] = useState(false);

  // Google-Maps-style LOD state (1 = Overview, 2 = Exploration, 3 = Deep Zoom)
  const [lod, setLod] = useState(2);
  const [zoomK, setZoomK] = useState(1.25);
  const lodRef = useRef(2);
  const camRef = useRef({ k: 1.25, x: 0, y: 0 });
  const historyRef = useRef([]);
  const [canGoBack, setCanGoBack] = useState(false);
  const labelBoxesRef = useRef([]);
  const fittedRef = useRef(false);
  const zoomRafRef = useRef(null);

  const rawData = useMemo(() => {
    if (mode === "engine") return viewEngine(engine, graph);
    return viewGraph(graph, mode);
  }, [graph, engine, mode]);

  const data = useMemo(() => {
    if (roleFilter === "all") return rawData;
    const keep = new Set(
      rawData.nodes
        .filter((n) =>
          mode === "engine"
            ? String(n.type || n.kind || "").toLowerCase() === roleFilter
            : n.role === roleFilter,
        )
        .map((n) => n.id),
    );
    return {
      nodes: rawData.nodes.filter((n) => keep.has(n.id)),
      links: rawData.links.filter((l) => {
        const s = typeof l.source === "object" ? l.source.id : l.source;
        const t = typeof l.target === "object" ? l.target.id : l.target;
        return keep.has(s) && keep.has(t);
      }),
      clusters: rawData.clusters || [],
    };
  }, [rawData, roleFilter, mode]);

  const neighborMap = useMemo(() => {
    const map = new Map();
    for (const l of data.links) {
      const s = typeof l.source === "object" ? l.source.id : l.source;
      const t = typeof l.target === "object" ? l.target.id : l.target;
      if (!map.has(s)) map.set(s, new Set());
      if (!map.has(t)) map.set(t, new Set());
      map.get(s).add(t);
      map.get(t).add(s);
    }
    return map;
  }, [data.links]);

  const wrap = useRef(null);
  const fg = useRef(null);
  const [w, setW] = useState(900);

  useEffect(() => {
    const ro = new ResizeObserver(([e]) =>
      setW(Math.floor(e.contentRect.width)),
    );
    if (wrap.current) ro.observe(wrap.current);
    return () => ro.disconnect();
  }, []);

  const pushCameraHistory = useCallback(() => {
    historyRef.current.push({ ...camRef.current });
    if (historyRef.current.length > 15) historyRef.current.shift();
    setCanGoBack(true);
  }, []);

  const updateLodFromScale = useCallback((k) => {
    if (!Number.isFinite(k)) return;
    setZoomK(Number(k.toFixed(2)));
    const cur = lodRef.current;
    let next = cur;
    if (cur === 1) {
      if (k >= LOD_CONFIG.L3_ENTER) next = 3;
      else if (k >= LOD_CONFIG.L2_ENTER) next = 2;
    } else if (cur === 2) {
      if (k < LOD_CONFIG.L2_EXIT) next = 1;
      else if (k >= LOD_CONFIG.L3_ENTER) next = 3;
    } else if (cur === 3) {
      if (k < LOD_CONFIG.L2_EXIT) next = 1;
      else if (k < LOD_CONFIG.L3_EXIT) next = 2;
    }
    if (next !== cur) {
      lodRef.current = next;
      setLod(next);
    }
  }, []);

  // Defer setState out of ForceGraph2D's render cycle to prevent React setState-in-render errors
  const handleZoom = useCallback(
    ({ k, x, y }) => {
      camRef.current = { k, x, y };
      if (zoomRafRef.current) cancelAnimationFrame(zoomRafRef.current);
      zoomRafRef.current = requestAnimationFrame(() => {
        updateLodFromScale(k);
      });
    },
    [updateLodFromScale],
  );

  useEffect(() => {
    return () => {
      if (zoomRafRef.current) cancelAnimationFrame(zoomRafRef.current);
    };
  }, []);

  useEffect(() => {
    setSelected(null);
    setRoleFilter("all");
    fittedRef.current = false;
  }, [mode]);

  // Fit graph reliably once async data arrives or container resizes
  useEffect(() => {
    if (data.nodes.length === 0) return;
    const t = setTimeout(() => {
      if (!fittedRef.current) {
        fg.current?.zoomToFit?.(350, 60);
        fittedRef.current = true;
      }
    }, 220);
    return () => clearTimeout(t);
  }, [mode, w, data.nodes.length]);

  const zoomBy = useCallback(
    (factor) => {
      if (!fg.current) return;
      pushCameraHistory();
      const target = Math.min(
        LOD_CONFIG.MAX_ZOOM,
        Math.max(LOD_CONFIG.MIN_ZOOM, camRef.current.k * factor),
      );
      fg.current.zoom(target, 280);
    },
    [pushCameraHistory],
  );

  const fitScreen = useCallback(() => {
    pushCameraHistory();
    fg.current?.zoomToFit?.(400, 60);
  }, [pushCameraHistory]);

  const resetView = useCallback(() => {
    pushCameraHistory();
    setSelected(null);
    setRoleFilter("all");
    fg.current?.centerAt(0, 0, 350);
    fg.current?.zoomToFit?.(380, 60);
  }, [pushCameraHistory]);

  const centerGraph = useCallback(() => {
    pushCameraHistory();
    fg.current?.centerAt(0, 0, 350);
  }, [pushCameraHistory]);

  const focusNode = useCallback(
    (n, targetZoom = 2.6) => {
      if (!n || !Number.isFinite(n.x) || !Number.isFinite(n.y) || !fg.current)
        return;
      pushCameraHistory();
      setSelected(n);
      fg.current.centerAt(n.x, n.y, 450);
      fg.current.zoom(Math.max(camRef.current.k, targetZoom), 450);
    },
    [pushCameraHistory],
  );

  const goBackView = useCallback(() => {
    const prev = historyRef.current.pop();
    setCanGoBack(historyRef.current.length > 0);
    if (!prev || !fg.current) return;
    fg.current.centerAt(prev.x, prev.y, 380);
    fg.current.zoom(prev.k, 380);
  }, []);

  useEffect(() => {
    const onKey = (e) => {
      if (["INPUT", "TEXTAREA"].includes(document.activeElement?.tagName))
        return;
      if (e.key === "=" || e.key === "+") zoomBy(1.3);
      else if (e.key === "-") zoomBy(0.75);
      else if (e.key === "0") resetView();
      else if (e.key.toLowerCase() === "f") fitScreen();
      else if (e.key === "Escape") setSelected(null);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [zoomBy, resetView, fitScreen]);

  const find = (e) => {
    e.preventDefault();
    const s = q.trim().toLowerCase();
    if (!s) return;
    const n = data.nodes.find((x) => {
      const schemaText = getSchemaFields(x)
        .map((f) => `${f.name} ${f.type}`)
        .join(" ")
        .toLowerCase();
      return (
        String(x.name ?? x.label ?? "")
          .toLowerCase()
          .includes(s) ||
        String(x.id).toLowerCase().includes(s) ||
        String(x.phone ?? "").includes(s) ||
        schemaText.includes(s)
      );
    });
    setMiss(!n);
    if (n) focusNode(n, 2.65);
  };

  const { stats, shared } = graph;
  const nameOf = (id) => graph.nodes.find((n) => n.id === id)?.name ?? id;

  const nodeColor = (n) => {
    if (n.role === "engine") {
      return KIND_COLOR[n.kind] || KIND_COLOR[n.type] || "#38bdf8";
    }
    return ROLE[n.role]?.color || "#38bdf8";
  };

  const drawBackdrop = (ctx, globalScale) => {
    labelBoxesRef.current = [];
    if (!Number.isFinite(globalScale) || globalScale <= 0) return;
    const { x: cx, y: cy } = camRef.current;
    const halfW = w / globalScale;
    const halfH = 600 / globalScale;
    const step = globalScale > 2 ? 40 : globalScale > 0.8 ? 80 : 160;

    ctx.save();
    ctx.strokeStyle = "rgba(34, 211, 238, 0.05)";
    ctx.lineWidth = 1 / globalScale;
    const startX = Math.floor((cx - halfW) / step) * step;
    const startY = Math.floor((cy - halfH) / step) * step;
    for (let x = startX; x < cx + halfW; x += step) {
      ctx.beginPath();
      ctx.moveTo(x, cy - halfH);
      ctx.lineTo(x, cy + halfH);
      ctx.stroke();
    }
    for (let y = startY; y < cy + halfH; y += step) {
      ctx.beginPath();
      ctx.moveTo(cx - halfW, y);
      ctx.lineTo(cx + halfW, y);
      ctx.stroke();
    }

    if (lod === 1 && data.clusters?.length) {
      for (const cl of data.clusters) {
        ctx.beginPath();
        ctx.arc(cl.cx, cl.cy, cl.radius, 0, Math.PI * 2);
        ctx.fillStyle = cl.color + "10";
        ctx.fill();
        ctx.setLineDash([6 / globalScale, 4 / globalScale]);
        ctx.strokeStyle = cl.color + "55";
        ctx.lineWidth = 1.2 / globalScale;
        ctx.stroke();
        ctx.setLineDash([]);

        ctx.font = `600 ${12 / globalScale}px Inter, sans-serif`;
        ctx.textAlign = "center";
        ctx.fillStyle = cl.color;
        ctx.fillText(
          `${cl.label.toUpperCase()} (${cl.count})`,
          cl.cx,
          cl.cy - cl.radius - 8 / globalScale,
        );
      }
    }
    ctx.restore();
  };

  // Preserves exact 2D glowing node UI; never draws overlapping schema cards on zoom/hover
  const drawNode = (n, ctx, gs) => {
    if (!Number.isFinite(n.x) || !Number.isFinite(n.y) || !Number.isFinite(gs))
      return;

    const isSel = selected?.id === n.id;
    const isNeighbor = selected && neighborMap.get(selected.id)?.has(n.id);
    const dimmed = selected && !isSel && !isNeighbor;

    if (lod === 1 && mode !== "network" && !isSel && !isNeighbor) {
      if (n.role === "other") return;
      if (n.role === "engine" && (n.ctrl || 0) < 0.3) return;
    }

    const color = nodeColor(n);
    const alpha = dimmed ? 0.14 : 1;

    ctx.save();
    ctx.globalAlpha = alpha;

    const flagged = n.role !== "other";
    const r =
      n.role === "engine"
        ? 3.5 + (n.ctrl || 0.25) * 6
        : n.role === "handler"
          ? 8.5
          : flagged
            ? 5.5 + Math.min(6.5, Math.sqrt((n.volume || 0) / 1000) * 0.35)
            : 2.8 + (n.risk || 0) * 2.5;

    ctx.shadowColor = color;
    ctx.shadowBlur = isSel || hovered?.id === n.id ? 18 : flagged ? 10 : 0;

    if (flagged || isSel) {
      ctx.beginPath();
      ctx.arc(n.x, n.y, r + 2.5 / gs, 0, Math.PI * 2);
      ctx.strokeStyle = isSel ? "#ffffff" : color + "66";
      ctx.lineWidth = (isSel ? 1.8 : 0.9) / gs;
      ctx.stroke();
    }

    const grad = ctx.createRadialGradient(
      n.x - r * 0.3,
      n.y - r * 0.3,
      r * 0.1,
      n.x,
      n.y,
      r,
    );
    grad.addColorStop(0, "#ffffff");
    grad.addColorStop(0.35, color);
    grad.addColorStop(1, color + "99");
    ctx.beginPath();
    ctx.arc(n.x, n.y, r, 0, Math.PI * 2);
    ctx.fillStyle = grad;
    ctx.fill();
    ctx.shadowBlur = 0;

    const showLabel =
      isSel ||
      isNeighbor ||
      hovered?.id === n.id ||
      (lod >= 2 &&
        labelBoxesRef.current.length < LOD_CONFIG.MAX_LABELS_L2 &&
        (flagged || gs > 1.5));

    if (showLabel) {
      const txt = String(n.name || n.label || n.id || "");
      const clipped = txt.length > 22 ? txt.slice(0, 21) + "…" : txt;
      const fontSize = (flagged || isSel ? 10.5 : 8.5) / gs;
      ctx.font = `600 ${fontSize}px Inter, sans-serif`;
      const tw = ctx.measureText(clipped).width + 8 / gs;
      const th = fontSize + 5 / gs;
      const lx = n.x - tw / 2;
      const ly = n.y + r + 3 / gs;

      const overlaps =
        !isSel &&
        !hovered &&
        labelBoxesRef.current.some(
          (b) =>
            lx < b.x + b.w && lx + tw > b.x && ly < b.y + b.h && ly + th > b.y,
        );

      if (!overlaps) {
        labelBoxesRef.current.push({ x: lx, y: ly, w: tw, h: th });
        ctx.fillStyle = "rgba(10, 15, 28, 0.82)";
        drawRoundedRect(ctx, lx, ly, tw, th, 3 / gs);
        ctx.fill();
        ctx.fillStyle = isSel ? "#ffffff" : "#e2e8f0";
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.fillText(clipped, n.x, ly + th / 2);
      }
    }

    ctx.restore();
  };

  const selectedReasons = selected ? getReasons(selected) : [];
  const selectedSchema = selected ? getSchemaFields(selected) : [];
  const selectedRisk =
    selected?.risk != null
      ? Number(selected.risk).toFixed(2)
      : selected?.ctrl != null
        ? Number(selected.ctrl).toFixed(2)
        : selected?.role === "mule"
          ? (selected.passthrough || 0.85).toFixed(2)
          : "N/A";

  const connectedNodes = useMemo(() => {
    if (!selected) return [];
    const ids = neighborMap.get(selected.id);
    if (!ids) return [];
    return data.nodes.filter((n) => ids.has(n.id)).slice(0, 12);
  }, [selected, neighborMap, data.nodes]);

  const lodText =
    lod === 1
      ? "L1 · Overview (Clusters)"
      : lod === 2
        ? "L2 · Exploration (Labels)"
        : "L3 · Deep Zoom";

  return (
    <div className="panel neon-card graph-panel">
      <div className="graph-head">
        <div>
          <h2 className="panel-title">Mule network · 2D Explorer</h2>
          <p className="muted small">
            {transactions.length} transactions · {stats.accounts} accounts
          </p>
        </div>

        <form
          className={"graph-search" + (miss ? " miss" : "")}
          onSubmit={find}
          role="search"
        >
          <input
            value={q}
            onChange={(e) => {
              setQ(e.target.value);
              setMiss(false);
            }}
            placeholder="Search name, account, phone, or schema field"
            aria-label="Search the graph"
          />
          {q && (
            <button
              type="button"
              aria-label="Clear"
              onClick={() => {
                setQ("");
                setMiss(false);
              }}
            >
              ×
            </button>
          )}
        </form>

        <div className="seg">
          <button
            className={mode === "network" ? "on" : ""}
            onClick={() => setMode("network")}
          >
            Suspicious chain
          </button>
          <button
            className={mode === "all" ? "on" : ""}
            onClick={() => setMode("all")}
          >
            All accounts
          </button>
          <button
            className={mode === "engine" ? "on" : ""}
            onClick={() => setMode("engine")}
          >
            Engine graph
          </button>
        </div>
      </div>

      <div
        className="tl-filters"
        style={{ marginBottom: 10, display: "flex", gap: 6, flexWrap: "wrap" }}
      >
        {(mode === "engine"
          ? ["all", "account", "phone", "device", "ip_address", "vpa"]
          : ["all", "victim", "mule", "cashout", "handler", "other"]
        ).map((k) => (
          <button
            key={k}
            className={"chipbtn" + (roleFilter === k ? " on" : "")}
            style={{
              "--c": ROLE[k]?.color || KIND_COLOR[k] || "#22d3ee",
            }}
            onClick={() => setRoleFilter(k)}
          >
            <i />
            {k === "all"
              ? "All types"
              : ROLE[k]?.label || k.replaceAll("_", " ")}
          </button>
        ))}
      </div>

      {miss && (
        <div className="graph-search-msg">
          No account, entity, or schema field matches “{q}”.
        </div>
      )}

      {error && (
        <div
          className="status bad"
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            marginBottom: 10,
          }}
        >
          <span>Failed to load graph data: {error}</span>
          {onRetry && (
            <button className="mini" onClick={onRetry}>
              Retry
            </button>
          )}
        </div>
      )}

      <div
        ref={wrap}
        className="graph-canvas"
        style={{
          position: "relative",
          minHeight: 580,
          background:
            "radial-gradient(circle at 50% 45%, rgba(34,211,238,0.06), rgba(8,12,24,0.95) 75%)",
          borderRadius: 10,
          overflow: "hidden",
        }}
      >
        {loading && data.nodes.length === 0 && (
          <div
            className="muted small"
            style={{
              position: "absolute",
              inset: 0,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              zIndex: 5,
              pointerEvents: "none",
            }}
          >
            Loading graph data…
          </div>
        )}

        <div
          style={{
            position: "absolute",
            top: 12,
            left: 12,
            zIndex: 9,
            display: "flex",
            gap: 6,
            flexWrap: "wrap",
            alignItems: "center",
            background: "rgba(9, 14, 28, 0.88)",
            backdropFilter: "blur(8px)",
            padding: "6px 10px",
            borderRadius: 8,
            border: "1px solid rgba(34, 211, 238, 0.25)",
            fontSize: 12,
          }}
        >
          <span
            style={{
              color: lod === 3 ? "#2dd4bf" : lod === 2 ? "#38bdf8" : "#94a3b8",
              fontWeight: 600,
              marginRight: 4,
            }}
          >
            {lodText}
          </span>
          <span className="muted mono">({zoomK}x)</span>
          <button
            className="mini"
            onClick={() => zoomBy(1.35)}
            title="Zoom In (+)"
          >
            +
          </button>
          <button
            className="mini"
            onClick={() => zoomBy(0.72)}
            title="Zoom Out (-)"
          >
            −
          </button>
          <button
            className="mini"
            onClick={fitScreen}
            title="Fit to Screen (F)"
          >
            Fit
          </button>
          <button className="mini" onClick={centerGraph} title="Center Graph">
            Center
          </button>
          <button className="mini" onClick={resetView} title="Reset View (0)">
            Reset
          </button>
          {selected && (
            <button
              className="mini"
              onClick={() => focusNode(selected, 2.6)}
              title="Focus Selected Node"
            >
              Focus
            </button>
          )}
          {canGoBack && (
            <button
              className="mini"
              onClick={goBackView}
              title="Back to Previous View"
            >
              ← Back
            </button>
          )}
        </div>

        <ForceGraph2D
          ref={fg}
          graphData={data}
          width={w}
          height={580}
          backgroundColor="rgba(0,0,0,0)"
          minZoom={LOD_CONFIG.MIN_ZOOM}
          maxZoom={LOD_CONFIG.MAX_ZOOM}
          warmupTicks={80}
          cooldownTicks={40}
          d3VelocityDecay={0.35}
          onZoom={handleZoom}
          onRenderFramePre={drawBackdrop}
          nodeCanvasObject={drawNode}
          nodePointerAreaPaint={(n, color, ctx) => {
            if (!Number.isFinite(n.x) || !Number.isFinite(n.y)) return;
            ctx.fillStyle = color;
            ctx.beginPath();
            ctx.arc(n.x, n.y, 11, 0, Math.PI * 2);
            ctx.fill();
          }}
          linkCurvature={(l) => (l.kind === "shared" ? 0.35 : 0.14)}
          linkColor={(l) => {
            const s = typeof l.source === "object" ? l.source.id : l.source;
            const t = typeof l.target === "object" ? l.target.id : l.target;
            const rel = selected && (s === selected.id || t === selected.id);
            if (selected && !rel) return "rgba(100,116,139,0.08)";
            if (rel) return "#22d3ee";
            if (l.kind === "shared") return "rgba(167,139,250,0.65)";
            if (l.kind === "call") return "rgba(251,146,60,0.55)";
            return lod === 1
              ? "rgba(56,189,248,0.16)"
              : "rgba(56,189,248,0.32)";
          }}
          linkWidth={(l) => {
            const s = typeof l.source === "object" ? l.source.id : l.source;
            const t = typeof l.target === "object" ? l.target.id : l.target;
            if (selected && (s === selected.id || t === selected.id))
              return 2.2;
            return l.kind === "shared" || l.kind === "call" ? 1.3 : 0.9;
          }}
          linkDirectionalArrowLength={(l) =>
            l.kind === "flow" && lod >= 2 ? 4 : 0
          }
          linkDirectionalArrowRelPos={0.9}
          linkDirectionalParticles={(l) => {
            const s = typeof l.source === "object" ? l.source.id : l.source;
            const t = typeof l.target === "object" ? l.target.id : l.target;
            if (selected && (s === selected.id || t === selected.id)) return 3;
            return mode === "network" && l.kind === "flow" ? 1 : 0;
          }}
          linkDirectionalParticleWidth={2.2}
          linkDirectionalParticleSpeed={0.006}
          onNodeHover={(n) => setHovered(n || null)}
          onNodeClick={(n) =>
            setSelected((cur) => (cur?.id === n.id ? null : n))
          }
          onBackgroundClick={() => setSelected(null)}
          onEngineStop={() => {
            if (!fittedRef.current && data.nodes.length > 0) {
              fg.current?.zoomToFit?.(350, 60);
              fittedRef.current = true;
            }
          }}
        />

        {/* ONE schema panel at a time, strictly on intentional click, pinned to corner */}
        {selected && (
          <div
            className="node-card"
            style={{
              position: "absolute",
              top: 12,
              right: 12,
              width: 330,
              maxHeight: "calc(100% - 24px)",
              overflowY: "auto",
              zIndex: 10,
              background: "rgba(9, 14, 28, 0.94)",
              border: "1px solid rgba(34, 211, 238, 0.35)",
            }}
          >
            <button
              className="x"
              onClick={() => setSelected(null)}
              aria-label="Exit focus"
              title="Exit focus (Esc)"
            >
              ×
            </button>
            <div
              className="nc-role"
              style={{ color: nodeColor(selected), marginBottom: 6 }}
            >
              {selected.role === "engine"
                ? String(selected.type || selected.kind || "node").replaceAll(
                    "_",
                    " ",
                  )
                : ROLE[selected.role]?.label}
            </div>

            <table
              className="audit-table"
              style={{ width: "100%", fontSize: 12, marginBottom: 10 }}
            >
              <tbody>
                <tr>
                  <td className="muted">Account Name</td>
                  <td>
                    <b>{selected.name || selected.label || "Unknown"}</b>
                  </td>
                </tr>
                <tr>
                  <td className="muted">Account / ID</td>
                  <td className="mono">{selected.id}</td>
                </tr>
                <tr>
                  <td className="muted">Risk Score</td>
                  <td>
                    <b>{selectedRisk}</b>
                  </td>
                </tr>
                {selected.inSum != null && (
                  <tr>
                    <td className="muted">Received / Sent</td>
                    <td>
                      {inr(selected.inSum)} / {inr(selected.outSum)}
                    </td>
                  </tr>
                )}
              </tbody>
            </table>

            {selectedSchema.length > 0 && (
              <div style={{ fontSize: 12, marginBottom: 10 }}>
                <div className="muted" style={{ marginBottom: 4 }}>
                  Schema / Attributes
                </div>
                <table
                  className="audit-table"
                  style={{ width: "100%", fontSize: 11 }}
                >
                  <tbody>
                    {selectedSchema.map((f) => (
                      <tr key={f.name}>
                        <td className="mono" style={{ width: 28 }}>
                          {f.key && (
                            <span
                              style={{
                                color: f.key === "PK" ? "#fbbf24" : "#22d3ee",
                                fontWeight: 700,
                              }}
                            >
                              {f.key}
                            </span>
                          )}
                        </td>
                        <td className="mono">{f.name}</td>
                        <td
                          className="mono muted"
                          style={{ textAlign: "right" }}
                        >
                          {f.type}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            <div style={{ fontSize: 12, marginBottom: 10 }}>
              <div className="muted" style={{ marginBottom: 4 }}>
                Suspicious Reasons
              </div>
              {selectedReasons.length > 0 ? (
                <ul className="reasons" style={{ margin: 0, paddingLeft: 16 }}>
                  {selectedReasons.map((r, i) => (
                    <li key={i}>{r}</li>
                  ))}
                </ul>
              ) : (
                <p className="muted small" style={{ margin: 0 }}>
                  No suspicious flags recorded.
                </p>
              )}
            </div>

            {connectedNodes.length > 0 && (
              <div style={{ fontSize: 12 }}>
                <div className="muted" style={{ marginBottom: 6 }}>
                  Connected Accounts ({connectedNodes.length})
                </div>
                <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                  {connectedNodes.map((cn) => (
                    <button
                      key={cn.id}
                      className="mini"
                      onClick={() => focusNode(cn, 2.4)}
                    >
                      {cn.name || cn.label || String(cn.id).slice(0, 10)}
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      <p className="muted small" style={{ marginTop: 8 }}>
        <b>Navigation:</b> Scroll / Trackpad Pinch = Zoom · Drag = Pan · Click
        Node = Open Schema · Keys: <code>+</code>/<code>−</code> Zoom,{" "}
        <code>F</code> Fit, <code>0</code> Reset, <code>Esc</code> Close.
      </p>

      {(shared.length > 0 || graph.handler) && (
        <div className="evidence">
          <h3>Link evidence</h3>
          {graph.handler && (
            <p>
              The phone <span className="mono">{graph.handler.phone}</span>{" "}
              called {graph.handler.mules.length} of the flagged accounts within
              10 minutes after each received money.
            </p>
          )}
          {shared.map((s, i) => (
            <p key={i}>
              <b>{nameOf(s.source)}</b> and <b>{nameOf(s.target)}</b> paid from
              the same device (
              <span className="mono">{s.device.slice(0, 8)}…</span>).
            </p>
          ))}
        </div>
      )}
    </div>
  );
}
