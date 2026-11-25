import { useEffect, useMemo, useRef, useState } from "react";
import ForceGraph2D from "react-force-graph-2d";
import {
  buildGraph,
  viewGraph,
  viewEngine,
  ROLE,
  KIND_COLOR,
} from "../graphLogic.js";

// Canvas drawing cannot use CSS variables, so pick ink by theme.
const isLight = () => document.documentElement.getAttribute("data-theme") === "light";
const ink = (a = 1) => (isLight() ? `rgba(15,23,42,${a})` : `rgba(255,255,255,${a})`);
const inr = (n) => "₹" + Math.round(n).toLocaleString("en-IN");
const hhmm = (t) => new Date(t).toISOString().slice(11, 16);

export default function GraphView({ transactions, calls, scores, engine }) {
  const graph = useMemo(
    () => buildGraph(transactions, calls, scores),
    [transactions, calls, scores],
  );
  const [mode, setMode] = useState("network"); // network | all | engine
  const [selected, setSelected] = useState(null);
  const [q, setQ] = useState("");
  const [miss, setMiss] = useState(false);
  const data = useMemo(
    () => (mode === "engine" ? viewEngine(engine) : viewGraph(graph, mode)),
    [graph, engine, mode],
  );
  const wrap = useRef(null);
  const fg = useRef(null);
  const [w, setW] = useState(800);

  useEffect(() => {
    const ro = new ResizeObserver(([e]) =>
      setW(Math.floor(e.contentRect.width)),
    );
    if (wrap.current) ro.observe(wrap.current);
    return () => ro.disconnect();
  }, []);
  useEffect(() => {
    setSelected(null);
    const t = setTimeout(() => fg.current?.zoomToFit(400, 70), 350);
    return () => clearTimeout(t);
  }, [mode, w]);

  // redraw the canvas when the theme is switched
  useEffect(() => {
    const mo = new MutationObserver(() => fg.current?.refresh?.());
    mo.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    return () => mo.disconnect();
  }, []);

  // "Search from graph": find an account / person / phone and zoom to it
  const find = (e) => {
    e.preventDefault();
    const s = q.trim().toLowerCase();
    if (!s) return;
    const n = data.nodes.find(
      (x) =>
        String(x.name ?? x.label ?? "").toLowerCase().includes(s) ||
        String(x.id).toLowerCase().includes(s) ||
        String(x.phone ?? "").includes(s),
    );
    setMiss(!n);
    if (!n) return;
    setSelected(n);
    if (n.x != null) {
      fg.current?.centerAt(n.x, n.y, 500);
      fg.current?.zoom(3, 500);
    }
  };

  const { stats, shared } = graph;
  const nameOf = (id) => graph.nodes.find((n) => n.id === id)?.name ?? id;

  const drawNode = (n, ctx, gs) => {
    if (n.role === "engine") {
      const r = 2.5 + (n.ctrl || 0) * 9;
      const color = KIND_COLOR[n.kind] || "#94a3b8";
      ctx.save();
      ctx.shadowColor = color;
      ctx.shadowBlur = n.ctrl > 0.5 ? 10 : 0;
      ctx.beginPath();
      ctx.arc(n.x, n.y, r, 0, 2 * Math.PI);
      ctx.fillStyle = color + "b3";
      ctx.fill();
      ctx.restore();
      if (selected?.id === n.id) {
        ctx.beginPath();
        ctx.arc(n.x, n.y, r + 3, 0, 2 * Math.PI);
        ctx.strokeStyle = ink(1);
        ctx.lineWidth = 1.2 / gs;
        ctx.stroke();
      }
      if (gs > (n.kind === "account" ? 1.4 : 2.6)) {
        ctx.font = `${9 / gs}px Inter, sans-serif`;
        ctx.textAlign = "center";
        ctx.textBaseline = "top";
        ctx.fillStyle = ink(0.6);
        ctx.fillText(
          n.kind === "account" ? "…" + n.label.slice(-4) : n.label,
          n.x,
          n.y + r + 2 / gs,
        );
      }
      return;
    }
    const flagged = n.role !== "other";
    const r =
      n.role === "handler"
        ? 9
        : flagged
          ? 6 + Math.min(8, Math.sqrt(n.volume / 1000) * 0.45)
          : 2.5 + (n.risk || 0) * 3;
    const color = ROLE[n.role].color;
    ctx.save();
    ctx.shadowColor = color;
    ctx.shadowBlur = flagged ? 14 : 0;
    ctx.beginPath();
    ctx.arc(n.x, n.y, r, 0, 2 * Math.PI);
    ctx.fillStyle = color + (flagged ? "cc" : "99");
    ctx.fill();
    ctx.restore();
    if (selected?.id === n.id) {
      ctx.beginPath();
      ctx.arc(n.x, n.y, r + 3, 0, 2 * Math.PI);
      ctx.strokeStyle = ink(1);
      ctx.lineWidth = 1.2 / gs;
      ctx.stroke();
    }
    if (flagged || gs > 2) {
      ctx.font = `${(flagged ? 11 : 9) / gs}px Inter, sans-serif`;
      ctx.textAlign = "center";
      ctx.textBaseline = "top";
      ctx.fillStyle = flagged
        ? ink(0.88)
        : ink(0.55);
      ctx.fillText(n.name, n.x, n.y + r + 3 / gs);
    }
  };
  const drawLabel = (l, ctx, gs) => {
    if (
      !l.label ||
      typeof l.source !== "object" ||
      (mode === "all" && gs < 1.6)
    )
      return;
    ctx.font = `${9 / gs}px Inter, sans-serif`;
    ctx.textAlign = "center";
    ctx.textBaseline = "bottom";
    ctx.fillStyle = ink(0.5);
    ctx.fillText(
      l.label,
      (l.source.x + l.target.x) / 2,
      (l.source.y + l.target.y) / 2 - 3 / gs,
    );
  };

  return (
    <div className="panel neon-card graph-panel">
      <div className="graph-head">
        <div>
          <h2 className="panel-title">Mule network</h2>
          <p className="muted small">
            Synthetic case · {transactions.length} transactions ·{" "}
            {stats.accounts} accounts
          </p>
        </div>
        <form className={"graph-search" + (miss ? " miss" : "")} onSubmit={find} role="search">
          <input
            value={q}
            onChange={(e) => { setQ(e.target.value); setMiss(false); }}
            placeholder="Search from graph (name, account, phone)"
            aria-label="Search the graph"
          />
          {q && <button type="button" aria-label="Clear" onClick={() => { setQ(""); setMiss(false); }}>×</button>}
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

      {miss && <div className="graph-search-msg">No account, name or phone matches “{q}” in this view.</div>}

      {mode === "engine" ? (
        <div className="stat-row">
          <div>
            <b>{data.nodes.length}</b>
            <span>nodes (top by controller score)</span>
          </div>
          <div>
            <b>{data.links.length}</b>
            <span>edges</span>
          </div>
          <div>
            <b>{data.nodes.filter((n) => n.kind === "account").length}</b>
            <span>accounts</span>
          </div>
        </div>
      ) : (
        <div className="stat-row">
          <div>
            <b>{stats.flagged}</b>
            <span>accounts flagged</span>
          </div>
          {graph.handler && (
            <div>
              <b>1</b>
              <span>likely handler</span>
            </div>
          )}
          <div>
            <b>{inr(stats.entered)}</b>
            <span>entered the chain</span>
          </div>
          <div>
            <b>{inr(stats.routed)}</b>
            <span>reached the end</span>
          </div>
          {stats.from && (
            <div>
              <b>
                {hhmm(stats.from)}–{hhmm(stats.to)}
              </b>
              <span>UTC window</span>
            </div>
          )}
        </div>
      )}

      <div ref={wrap} className="graph-canvas">
        <ForceGraph2D
          ref={fg}
          graphData={data}
          width={w}
          height={mode === "network" ? 380 : mode === "engine" ? 600 : 560}
          backgroundColor="rgba(0,0,0,0)"
          nodeRelSize={6}
          nodeCanvasObject={drawNode}
          nodePointerAreaPaint={(n, color, ctx) => {
            ctx.fillStyle = color;
            ctx.beginPath();
            ctx.arc(n.x, n.y, 12, 0, 2 * Math.PI);
            ctx.fill();
          }}
          linkColor={(l) =>
            l.kind === "link"
              ? "rgba(167,139,250,.22)"
              : l.kind === "shared"
                ? "rgba(167,139,250,.9)"
                : l.kind === "call"
                  ? "rgba(251,146,60,.6)"
                  : ink(0.28)
          }
          linkWidth={(l) =>
            l.kind === "shared"
              ? 1.4
              : l.kind === "call"
                ? 1.1
                : Math.max(0.6, Math.log10(l.total) - 3)
          }
          linkLineDash={(l) =>
            l.kind === "shared" ? [4, 3] : l.kind === "call" ? [2, 3] : null
          }
          linkCurvature={(l) => (l.kind === "shared" ? 0.8 : 0)}
          linkDirectionalArrowLength={(l) =>
            l.kind !== "flow" ? 0 : mode === "network" ? 6 : 3
          }
          linkDirectionalArrowRelPos={0.92}
          linkCanvasObjectMode={() => "after"}
          linkCanvasObject={drawLabel}
          onNodeClick={(n) => setSelected(n)}
          onBackgroundClick={() => setSelected(null)}
          cooldownTicks={mode === "network" ? 60 : 160}
          onEngineStop={() => mode === "all" && fg.current?.zoomToFit(400, 50)}
        />
        {selected && (
          <div className="node-card">
            <button
              className="x"
              onClick={() => setSelected(null)}
              aria-label="Close"
            >
              ×
            </button>
            <div
              className="nc-role"
              style={{
                color:
                  selected.role === "engine"
                    ? KIND_COLOR[selected.kind]
                    : ROLE[selected.role].color,
              }}
            >
              {selected.role === "engine"
                ? selected.kind.replace("_", " ")
                : ROLE[selected.role].label}
            </div>
            <h3>
              {selected.role === "engine" ? selected.label : selected.name}
            </h3>
            <div className="mono small muted">{selected.id}</div>
            {selected.role === "engine" ? (
              <>
                <dl>
                  <dt>Controller</dt>
                  <dd>{selected.ctrl.toFixed(2)}</dd>
                  {selected.risk != null && (
                    <>
                      <dt>Risk</dt>
                      <dd>{selected.risk.toFixed(2)}</dd>
                    </>
                  )}
                  <dt>Cluster</dt>
                  <dd>{selected.cluster}</dd>
                </dl>
                {selected.reasons?.length > 0 && (
                  <ul className="reasons">
                    {selected.reasons.map((r) => (
                      <li key={r}>{r}</li>
                    ))}
                  </ul>
                )}
              </>
            ) : selected.role === "handler" ? (
              <dl>
                <dt>Phone</dt>
                <dd className="mono">{selected.phone}</dd>
                <dt>Called</dt>
                <dd>
                  {selected.called} flagged accounts, each within 10 minutes of
                  a deposit
                </dd>
              </dl>
            ) : (
              <>
                <dl>
                  <dt>Received</dt>
                  <dd>
                    {inr(selected.inSum)}{" "}
                    <span className="muted">({selected.inCnt})</span>
                  </dd>
                  <dt>Sent</dt>
                  <dd>
                    {inr(selected.outSum)}{" "}
                    <span className="muted">({selected.outCnt})</span>
                  </dd>
                  {selected.role === "mule" && (
                    <>
                      <dt>Passed on</dt>
                      <dd>
                        {Math.round(selected.passthrough * 100)}% of what it
                        received
                      </dd>
                    </>
                  )}
                  {(selected.cashIn > 0 || selected.cashOut > 0) && (
                    <>
                      <dt>Cash</dt>
                      <dd>
                        {selected.cashIn > 0 && `${inr(selected.cashIn)} in `}
                        {selected.cashOut > 0 && `${inr(selected.cashOut)} out`}
                      </dd>
                    </>
                  )}
                  {selected.risk != null && (
                    <>
                      <dt>Engine risk</dt>
                      <dd>{selected.risk.toFixed(2)}</dd>
                    </>
                  )}
                </dl>
                {selected.reasons?.length > 0 && (
                  <ul className="reasons">
                    {selected.reasons.map((r) => (
                      <li key={r}>{r}</li>
                    ))}
                  </ul>
                )}
              </>
            )}
          </div>
        )}
      </div>

      <div className="legend">
        {mode === "engine" ? (
          Object.entries(KIND_COLOR).map(([k, c]) => (
            <span key={k}>
              <i style={{ background: c }} />
              {k.replace("_", " ")}
            </span>
          ))
        ) : (
          <>
            {Object.entries(ROLE).map(([k, v]) => (
              <span key={k}>
                <i style={{ background: v.color }} />
                {v.label}
              </span>
            ))}
            <span>
              <i className="dash" />
              Shared device / IP
            </span>
            <span>
              <i className="dash orange" />
              Calls
            </span>
          </>
        )}
      </div>

      {(shared.length > 0 || graph.handler) && (
        <div className="evidence">
          <h3>Link evidence</h3>
          {graph.handler && (
            <p>
              The phone <span className="mono">{graph.handler.phone}</span>{" "}
              called {graph.handler.mules.length} of the flagged accounts within
              10 minutes after each received money. It never appears in any
              payment, only in the call records.
            </p>
          )}
          {shared.map((s, i) => (
            <p key={i}>
              <b>{nameOf(s.source)}</b> and <b>{nameOf(s.target)}</b> paid from
              the same device (
              <span className="mono">{s.device.slice(0, 8)}…</span>)
              {s.ips.length > 0 && (
                <>
                  {" "}
                  and the same IP (<span className="mono">{s.ips[0]}</span>)
                </>
              )}
              .
            </p>
          ))}
        </div>
      )}
      {mode === "engine" && (
        <p className="muted small note">
          This is the correlation engine's own graph, as computed. Node size is
          its controller score, which is still being tuned; the Suspicious chain
          view is the reliable one.
        </p>
      )}
      <p className="muted small note">
        Roles are a heuristic: an account that forwards at least 80% of what it
        receives, moving ₹1 lakh or more, is flagged as a mule. "Engine risk" is
        the score from the correlation engine.
      </p>
    </div>
  );
}
