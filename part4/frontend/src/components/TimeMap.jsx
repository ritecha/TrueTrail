import { useEffect, useMemo, useRef, useState } from "react";
import {
  MapContainer,
  TileLayer,
  CircleMarker,
  Popup,
  Polyline,
} from "react-leaflet";
import "leaflet/dist/leaflet.css";

const utc = (t) => String(t).replace("T", " ").replace("Z", " UTC");
const TYPES = {
  UPI: { label: "UPI payment", color: "#f472b6" },
  NEFT: { label: "Bank transfer", color: "#fb7185" },
  CALL: { label: "Call", color: "#22d3ee" },
  IP_SESSION: { label: "IP session", color: "#fbbf24" },
  TOWER_PING: { label: "Tower ping", color: "#a78bfa" },
};
const DEFAULT_ON = ["UPI", "NEFT", "CALL", "IP_SESSION"]; // pings are noisy, off by default

const day = (t) =>
  new Date(t).toLocaleDateString("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  });
const clock = (t) => String(t).slice(11, 16) + " UTC";
const mins = (a, b) =>
  Math.max(0, Math.round((Date.parse(b) - Date.parse(a)) / 60000));

function describe(e) {
  const x = e.entities || {};
  const inr = e.amount ? "₹" + e.amount.toLocaleString("en-IN") : null;
  switch (e.type) {
    case "UPI":
    case "NEFT":
      return { title: inr ?? "Payment", meta: `Paid to ${x.payee_id}` };
    case "CALL":
      return {
        title: x.direction === "IN" ? "Incoming call" : "Outgoing call",
        meta: `${x.counterparty} · ${mins(e.start_utc, e.end_utc)} min`,
      };
    case "IP_SESSION":
      return {
        title: `${mins(e.start_utc, e.end_utc)} min session`,
        meta: `${x.ip} → ${x.dest_ip}`,
      };
    default:
      return {
        title: "Tower ping",
        meta: e.geo
          ? `Near ${e.geo.lat.toFixed(3)}, ${e.geo.lon.toFixed(3)} (±${e.geo.radius_m} m)`
          : "",
      };
  }
}

function Item({ e, side }) {
  const ref = useRef(null);
  const [seen, setSeen] = useState(false);
  useEffect(() => {
    const io = new IntersectionObserver(
      ([en]) => {
        if (en.isIntersecting) {
          setSeen(true);
          io.disconnect();
        }
      },
      { threshold: 0.2, rootMargin: "0px 0px -6% 0px" },
    );
    io.observe(ref.current);
    return () => io.disconnect();
  }, []);
  const t = TYPES[e.type] ?? { label: e.type, color: "#94a3b8" };
  const d = describe(e);
  return (
    <li
      ref={ref}
      className={`tl2-item ${side}${seen ? " in-view" : ""}`}
      style={{ "--c": t.color }}
    >
      <div className="tl2-card">
        <div className="tl2-top">
          <span className="tl2-badge">{t.label}</span>
          <time className="mono">{clock(e.start_utc)}</time>
        </div>
        <div className="tl2-title">{d.title}</div>
        <div className="tl2-meta">{d.meta}</div>
      </div>
    </li>
  );
}

export function TimelineView({ data }) {
  const [on, setOn] = useState(() => new Set(DEFAULT_ON));
  const counts = useMemo(() => {
    const c = {};
    data.events.forEach((e) => (c[e.type] = (c[e.type] || 0) + 1));
    return c;
  }, [data]);

  const rows = useMemo(() => {
    const list = [...data.events]
      .filter((e) => on.has(e.type))
      .sort((a, b) => a.start_utc.localeCompare(b.start_utc));
    const out = [];
    let last = "",
      n = 0;
    for (const e of list) {
      const dy = day(e.start_utc);
      if (dy !== last) {
        out.push({ day: dy });
        last = dy;
      }
      out.push({ e, side: n++ % 2 ? "right" : "left" });
    }
    return out;
  }, [data, on]);

  const toggle = (k) =>
    setOn((s) => {
      const n = new Set(s);
      n.has(k) ? n.delete(k) : n.add(k);
      return n;
    });

  return (
    <div className="panel neon-card">
      <h2 className="panel-title">Event reconstruction</h2>
      <p className="muted small">
        Case {data.case_id} · {rows.filter((r) => r.e).length} of{" "}
        {data.events.length} events shown
      </p>

      {data.sessions?.map((s) => (
        <div className="status warn" key={s.session_id}>
          {s.type.replace("_", " ")} · {s.duration_h} h · {utc(s.start_utc)}
          <div className="chips">
            {s.flags.map((f) => (
              <span key={f}>{f.replaceAll("_", " ")}</span>
            ))}
          </div>
        </div>
      ))}

      <div className="tl-filters">
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

      <ol className="tl2">
        {rows.map((r, i) =>
          r.day ? (
            <li className="tl2-day" key={"d" + i}>
              <span>{r.day}</span>
            </li>
          ) : (
            <Item key={r.e.event_id} e={r.e} side={r.side} />
          ),
        )}
      </ol>
    </div>
  );
}

export function MapView({ data }) {
  const feats = data.geo_tracks?.[0]?.geojson?.features ?? [];
  const path =
    feats
      .find((f) => f.properties.kind === "path")
      ?.geometry.coordinates.map((c) => [c[1], c[0]]) ?? [];
  const pings = feats.filter((f) => f.properties.kind === "ping");
  return (
    <div
      className="panel neon-card"
      style={{ padding: 0, overflow: "hidden", height: 560 }}
    >
      <MapContainer
        center={path[0] ?? [28.75, 77.05]}
        zoom={11}
        style={{ height: "100%", width: "100%", background: "var(--bg-base)" }}
      >
        <TileLayer
          url="https://tile.openstreetmap.org/{z}/{x}/{y}.png"
          attribution="&copy; OpenStreetMap contributors"
        />
        <Polyline
          positions={path}
          pathOptions={{ color: "#22d3ee", weight: 2, opacity: 0.7 }}
        />
        {pings.map((p, i) => (
          <CircleMarker
            key={i}
            center={[p.geometry.coordinates[1], p.geometry.coordinates[0]]}
            radius={5}
            pathOptions={{
              color: "#f472b6",
              fillColor: "#f472b6",
              fillOpacity: 0.7,
              weight: 1,
            }}
          >
            <Popup>{utc(p.properties.time_utc)}</Popup>
          </CircleMarker>
        ))}
      </MapContainer>
    </div>
  );
}
