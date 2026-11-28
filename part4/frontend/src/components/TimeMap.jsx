import { useEffect, useMemo, useRef, useState } from "react";
import {
  MapContainer,
  TileLayer,
  CircleMarker,
  Popup,
  Polyline,
} from "react-leaflet";
import "leaflet/dist/leaflet.css";

const TYPES = {
  UPI: { label: "UPI payment", color: "#f472b6" },
  NEFT: { label: "Bank transfer", color: "#fb7185" },
  CALL: { label: "Call", color: "#22d3ee" },
  IP_SESSION: { label: "IP session", color: "#fbbf24" },
  TOWER_PING: { label: "Tower ping", color: "#a78bfa" },
};
const DEFAULT_ON = ["UPI", "NEFT", "CALL", "IP_SESSION"];

const TYPE_MAP = {
  cdr: "CALL",
  call: "CALL",
  ipdr: "IP_SESSION",
  ip_session: "IP_SESSION",
  ping: "TOWER_PING",
  tower_ping: "TOWER_PING",
  upi: "UPI",
  upi_transaction: "UPI",
  neft: "NEFT",
  bank_transaction: "NEFT",
  transaction: "UPI",
};

const normType = (raw) => {
  const k = String(raw || "").toLowerCase();
  if (TYPE_MAP[k]) return TYPE_MAP[k];
  const up = k.toUpperCase();
  return TYPES[up] ? up : up || "TOWER_PING";
};

const toDate = (t) => {
  if (t == null) return null;
  if (/^\d{9,10}(\.\d+)?$/.test(String(t).trim())) {
    return new Date(Number(t) * 1000);
  }
  const d = new Date(t);
  return Number.isNaN(d.getTime()) ? null : d;
};

const utc = (t) => {
  const d = toDate(t);
  return d
    ? d.toISOString().replace("T", " ").slice(0, 19) + " UTC"
    : "Unknown";
};

const shortTime = (ms) => {
  const d = new Date(ms);
  const mon = d.toLocaleDateString("en-GB", {
    day: "2-digit",
    month: "short",
    timeZone: "UTC",
  });
  return `${mon} · ${d.toISOString().slice(11, 16)}`;
};

function getEntityKey(e) {
  const x = e.entities || e.attributes || {};
  return (
    x.payee_id ||
    x.receiver ||
    x.counterparty ||
    x.dest_ip ||
    e.counterparty ||
    e.victim_id ||
    null
  );
}

function describe(e) {
  const x = e.entities || e.attributes || {};
  const inr = e.amount ? "₹" + Number(e.amount).toLocaleString("en-IN") : null;
  switch (e.type) {
    case "UPI":
    case "NEFT":
      return {
        line1: inr ?? "Payment",
        line2: `→ ${x.payee_id || x.receiver || e.counterparty || "Unknown"}`,
      };
    case "CALL":
      return {
        line1: x.direction === "IN" ? "Incoming call" : "Outgoing call",
        line2: `${x.counterparty || e.counterparty || "Unknown"}`,
      };
    case "IP_SESSION":
      return {
        line1: "IP session",
        line2: `${x.ip || x.public_ip || e.victim_id || "Host"} → ${x.dest_ip || e.counterparty || "Unknown"}`,
      };
    default:
      return {
        line1: "Tower ping",
        line2:
          e.latitude != null && e.longitude != null
            ? `${Number(e.latitude).toFixed(3)}, ${Number(e.longitude).toFixed(3)}`
            : e.source_file || "Ping",
      };
  }
}

// Snake layout constants
const ROW_SPACING = 152; // Generous vertical distance between parallel rows
const TOP_OFFSET = 52;
const BOTTOM_PAD = 96;
const PAD_X = 76; // Leaves clean margin for smooth left/right U-turn curves
const U_EXTENT = 56; // Bézier curve horizontal bulge for smooth U-turn

export function TimelineView({ data }) {
  const [on, setOn] = useState(() => new Set(DEFAULT_ON));
  const [picked, setPicked] = useState(null);
  const [visibleLimit, setVisibleLimit] = useState(32);
  const containerRef = useRef(null);
  const [width, setWidth] = useState(900);

  useEffect(() => {
    if (!containerRef.current) return;
    const measure = () => {
      if (containerRef.current) {
        setWidth(Math.max(320, containerRef.current.clientWidth));
      }
    };
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(containerRef.current);
    return () => ro.disconnect();
  }, []);

  const normalizedEvents = useMemo(() => {
    const raw = Array.isArray(data?.events) ? data.events : [];
    return raw
      .map((e, idx) => {
        const sDate = toDate(e.start_utc || e.timestamp_utc || e.timestamp);
        if (!sDate) return null;
        const eDate = toDate(e.end_utc) || sDate;
        const startMs = sDate.getTime();
        const endMs = Math.max(startMs, eDate.getTime());
        return {
          ...e,
          event_id: e.event_id || `evt_${idx}`,
          type: normType(e.type || e.event_type),
          startMs,
          endMs,
        };
      })
      .filter(Boolean);
  }, [data]);

  const counts = useMemo(() => {
    const c = {};
    normalizedEvents.forEach((e) => (c[e.type] = (c[e.type] || 0) + 1));
    return c;
  }, [normalizedEvents]);

  const filtered = useMemo(
    () =>
      normalizedEvents
        .filter((e) => on.has(e.type))
        .sort((a, b) => a.startMs - b.startMs),
    [normalizedEvents, on],
  );

  const visibleEvents = useMemo(
    () => filtered.slice(0, visibleLimit),
    [filtered, visibleLimit],
  );

  // Compute responsive columns & exact (x, y) coordinates + single continuous SVG snake path
  const layout = useMemo(() => {
    const innerW = Math.max(180, width - PAD_X * 2);
    const cols = Math.max(1, Math.min(5, Math.floor(innerW / 185) + 1));
    const colStep = cols > 1 ? innerW / (cols - 1) : 0;
    const boxW = Math.min(156, Math.max(116, cols > 1 ? colStep - 24 : 180));

    const placed = visibleEvents.map((e, idx) => {
      const row = Math.floor(idx / cols);
      const posInRow = idx % cols;
      const rtl = row % 2 === 1 && cols > 1;
      const col = rtl ? cols - 1 - posInRow : posInRow;
      const x = cols === 1 ? width / 2 : PAD_X + col * colStep;
      const y = TOP_OFFSET + row * ROW_SPACING;
      return { e, idx, row, col, rtl, x, y };
    });

    const totalRows = placed.length > 0 ? placed[placed.length - 1].row + 1 : 1;
    const totalHeight = TOP_OFFSET + (totalRows - 1) * ROW_SPACING + BOTTOM_PAD;

    // Build ONE continuous SVG snake path + directional arrowheads
    let pathD = "";
    const arrows = [];

    if (placed.length > 0) {
      if (cols === 1) {
        pathD = `M ${placed[0].x} ${placed[0].y}`;
        for (let i = 1; i < placed.length; i++) {
          pathD += ` L ${placed[i].x} ${placed[i].y}`;
          arrows.push({
            x: placed[i].x,
            y: (placed[i - 1].y + placed[i].y) / 2,
            rot: 90,
          });
        }
      } else {
        const leftX = PAD_X;
        const rightX = PAD_X + (cols - 1) * colStep;

        // Slight lead-in before first node like reference diagram
        pathD = `M ${Math.max(18, leftX - 34)} ${placed[0].y} L ${placed[0].x} ${placed[0].y}`;

        for (let r = 0; r < totalRows; r++) {
          const rowItems = placed.filter((p) => p.row === r);
          const rtl = r % 2 === 1;
          const y = TOP_OFFSET + r * ROW_SPACING;
          const hasNextRow = r < totalRows - 1;

          // Horizontal segments & arrows between adjacent nodes in this row
          for (let i = 0; i < rowItems.length - 1; i++) {
            const a = rowItems[i];
            const b = rowItems[i + 1];
            pathD += ` L ${b.x} ${b.y}`;
            arrows.push({
              x: (a.x + b.x) / 2,
              y,
              rot: rtl ? 180 : 0,
            });
          }

          // Smooth curved U-turn to next row
          if (hasNextRow) {
            const turnX = rtl ? leftX : rightX;
            const lastItem = rowItems[rowItems.length - 1];
            if (lastItem.x !== turnX) {
              pathD += ` L ${turnX} ${y}`;
            }
            const nextY = TOP_OFFSET + (r + 1) * ROW_SPACING;
            const ctrlX = rtl ? turnX - U_EXTENT : turnX + U_EXTENT;
            pathD += ` C ${ctrlX} ${y}, ${ctrlX} ${nextY}, ${turnX} ${nextY}`;
            arrows.push({
              x: rtl ? turnX - U_EXTENT * 0.74 : turnX + U_EXTENT * 0.74,
              y: (y + nextY) / 2,
              rot: 90,
            });
          }
        }
      }
    }

    return { placed, pathD, arrows, totalHeight, boxW };
  }, [visibleEvents, width]);

  const pickedEntity = picked ? getEntityKey(picked) : null;

  const toggle = (k) => {
    setVisibleLimit(32);
    setOn((s) => {
      const n = new Set(s);
      n.has(k) ? n.delete(k) : n.add(k);
      return n;
    });
  };

  return (
    <div className="panel neon-card">
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "baseline",
          flexWrap: "wrap",
          gap: 8,
        }}
      >
        <div>
          <h2 className="panel-title">Event reconstruction</h2>
          <p className="muted small">
            Case {data?.case_id || "active"} · Showing {visibleEvents.length} of{" "}
            {filtered.length} filtered events ({normalizedEvents.length} total)
          </p>
        </div>
      </div>

      <div className="tl-filters" style={{ marginBottom: 14 }}>
        {Object.entries(TYPES)
          .filter(([k]) => counts[k])
          .map(([k, t]) => (
            <button
              key={k}
              className={"chipbtn" + (on.has(k) ? " on" : "")}
              style={{ "--c": t.color }}
              onClick={() => toggle(k)}
            >
              <i />
              {t.label} <span>{counts[k]}</span>
            </button>
          ))}
      </div>

      {picked && (
        <div
          style={{
            marginBottom: 12,
            padding: "8px 12px",
            borderRadius: 8,
            border: `1px solid ${TYPES[picked.type]?.color || "var(--border-strong)"}`,
            background: "var(--bg-base)",
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            gap: 12,
            fontSize: 13,
          }}
        >
          <div>
            <b style={{ color: TYPES[picked.type]?.color }}>
              {TYPES[picked.type]?.label || picked.type}
            </b>{" "}
            · <span className="mono">{utc(picked.startMs)}</span> ·{" "}
            {describe(picked).line1} {describe(picked).line2}
            {picked.source_file && (
              <span className="muted small">
                {" "}
                · Source: {picked.source_file}
              </span>
            )}
          </div>
          <button className="mini" onClick={() => setPicked(null)}>
            Close
          </button>
        </div>
      )}

      {filtered.length === 0 ? (
        <p className="muted small">No events match the selected filters.</p>
      ) : (
        <div
          ref={containerRef}
          style={{
            maxHeight: "66vh",
            overflowY: "auto",
            overflowX: "hidden",
            borderRadius: 8,
            border: "1px solid var(--border-subtle)",
            background: "var(--bg-base)",
          }}
        >
          <div
            style={{
              position: "relative",
              width: "100%",
              height: layout.totalHeight,
            }}
          >
            {/* ONE continuous snake-shaped SVG path passing through every node */}
            <svg
              width={width}
              height={layout.totalHeight}
              style={{
                position: "absolute",
                inset: 0,
                pointerEvents: "none",
              }}
            >
              <path
                d={layout.pathD}
                fill="none"
                stroke="rgba(148, 163, 184, 0.55)"
                strokeWidth="2.5"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
              {layout.arrows.map((a, i) => (
                <polygon
                  key={i}
                  points="-5,-4 6,0 -5,4"
                  fill="rgba(226, 232, 240, 0.9)"
                  transform={`translate(${a.x}, ${a.y}) rotate(${a.rot})`}
                />
              ))}
            </svg>

            {/* Circular Nodes + Timestamps + Compact Explanation Boxes */}
            {layout.placed.map(({ e, x, y }) => {
              const meta = TYPES[e.type] ?? {
                label: e.type,
                color: "#94a3b8",
              };
              const summary = describe(e);
              const isPicked = picked?.event_id === e.event_id;
              const isRelated =
                picked &&
                pickedEntity &&
                getEntityKey(e) === pickedEntity &&
                !isPicked;
              const dimmed = picked && !isPicked && !isRelated;

              return (
                <div
                  key={e.event_id}
                  onClick={() =>
                    setPicked((cur) =>
                      cur?.event_id === e.event_id ? null : e,
                    )
                  }
                  style={{
                    position: "absolute",
                    left: x,
                    top: y,
                    transform: "translate(-50%, -14px)",
                    width: layout.boxW,
                    display: "flex",
                    flexDirection: "column",
                    alignItems: "center",
                    cursor: "pointer",
                    opacity: dimmed ? 0.3 : 1,
                    transition: "opacity 0.16s ease",
                  }}
                >
                  {/* Timestamp cleanly above node */}
                  <div
                    className="mono muted"
                    style={{
                      position: "absolute",
                      top: -20,
                      fontSize: 10.5,
                      whiteSpace: "nowrap",
                    }}
                  >
                    {shortTime(e.startMs)}
                  </div>

                  {/* Circular Event Node sitting directly on the snake line */}
                  <div
                    style={{
                      width: 28,
                      height: 28,
                      borderRadius: "50%",
                      background: meta.color,
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      boxShadow: isPicked
                        ? `0 0 0 3px #ffffff, 0 0 14px ${meta.color}`
                        : isRelated
                          ? `0 0 0 2px ${meta.color}, 0 0 10px ${meta.color}`
                          : `0 0 0 2px rgba(226,232,240,0.45), 0 0 10px ${meta.color}55`,
                      zIndex: 2,
                    }}
                  >
                    <div
                      style={{
                        width: 10,
                        height: 10,
                        borderRadius: "50%",
                        background: "#090e1c",
                      }}
                    />
                  </div>

                  {/* Small vertical stem connecting node to compact box */}
                  <div
                    style={{
                      width: 1.5,
                      height: 12,
                      background: meta.color + "aa",
                    }}
                  />

                  {/* Small, Compact 2-line Summary Box */}
                  <div
                    style={{
                      width: "100%",
                      padding: "5px 8px",
                      borderRadius: 7,
                      border: `1px solid ${
                        isPicked || isRelated ? meta.color : meta.color + "66"
                      }`,
                      background: "rgba(15, 23, 42, 0.86)",
                      textAlign: "center",
                      boxSizing: "border-box",
                    }}
                  >
                    <div
                      style={{
                        fontSize: 11.5,
                        fontWeight: 600,
                        color: meta.color,
                        whiteSpace: "nowrap",
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                        lineHeight: 1.25,
                      }}
                    >
                      {summary.line1}
                    </div>
                    <div
                      className="muted"
                      style={{
                        fontSize: 10.5,
                        whiteSpace: "nowrap",
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                        lineHeight: 1.25,
                      }}
                      title={summary.line2}
                    >
                      {summary.line2}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {visibleLimit < filtered.length && (
        <div
          style={{
            display: "flex",
            gap: 10,
            justifyContent: "center",
            marginTop: 12,
          }}
        >
          <button
            className="mini"
            onClick={() => setVisibleLimit((n) => n + 32)}
          >
            Load 32 more ({filtered.length - visibleLimit} remaining)
          </button>
          <button
            className="mini"
            onClick={() => setVisibleLimit(filtered.length)}
          >
            Show all ({filtered.length})
          </button>
        </div>
      )}
    </div>
  );
}

// export function MapView({ data }) {
//   const feats = data?.geo_tracks?.[0]?.geojson?.features ?? [];
//   const geoPath =
//     feats
//       .find((f) => f.properties?.kind === "path")
//       ?.geometry?.coordinates?.map((c) => [c[1], c[0]]) ?? [];
//   const geoPings = feats.filter((f) => f.properties?.kind === "ping");

//   const eventPts = (data?.events || [])
//     .filter((e) => e.latitude != null && e.longitude != null)
//     .map((e) => ({
//       pos: [Number(e.latitude), Number(e.longitude)],
//       label: `${e.event_type || "EVENT"} · ${utc(e.timestamp_utc || e.start_utc)}`,
//     }));

//   const trackPts = (data?.geo_tracks?.[0]?.points || []).map((p) => ({
//     pos: [Number(p.latitude), Number(p.longitude)],
//     label: `Tower ${p.tower_id || ""} · ${utc(p.timestamp)}`,
//   }));

//   const markers = geoPings.length
//     ? geoPings.map((p) => ({
//         pos: [p.geometry.coordinates[1], p.geometry.coordinates[0]],
//         label: utc(p.properties?.time_utc),
//       }))
//     : trackPts.length
//       ? trackPts
//       : eventPts;

//   const path = geoPath.length ? geoPath : markers.map((m) => m.pos);

//   return (
//     <div
//       className="panel neon-card"
//       style={{ padding: 0, overflow: "hidden", height: 560 }}
//     >
//       <MapContainer
//         center={path[0] ?? [28.6139, 77.209]}
//         zoom={5}
//         style={{ height: "100%", width: "100%", background: "var(--bg-base)" }}
//       >
//         <TileLayer
//           url="https://tile.openstreetmap.org/{z}/{x}/{y}.png"
//           attribution="&copy; OpenStreetMap contributors"
//         />
//         {path.length > 1 && (
//           <Polyline
//             positions={path}
//             pathOptions={{ color: "#22d3ee", weight: 2, opacity: 0.7 }}
//           />
//         )}
//         {markers.map((m, i) => (
//           <CircleMarker
//             key={i}
//             center={m.pos}
//             radius={5}
//             pathOptions={{
//               color: "#f472b6",
//               fillColor: "#f472b6",
//               fillOpacity: 0.7,
//               weight: 1,
//             }}
//           >
//             <Popup>{m.label}</Popup>
//           </CircleMarker>
//         ))}
//       </MapContainer>
//     </div>
//   );
// }
import GeoMap3D from "./GeoMap3D.jsx";

export function MapView({ data }) {
  return <GeoMap3D data={data} />;
}
