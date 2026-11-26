import { useEffect, useMemo, useRef, useState } from "react";
import {
  MapContainer,
  TileLayer,
  CircleMarker,
  Popup,
  Polyline,
} from "react-leaflet";
import "leaflet/dist/leaflet.css";

// ✅ Epoch (Unix) seconds ko sahi JS Date mein convert karne ke liye
const toDate = (t) => {
  if (t == null) return null;
  if (/^\d{9,10}(\.\d+)?$/.test(String(t).trim())) {
    return new Date(Number(t) * 1000);
  }
  const d = new Date(t);
  return Number.isNaN(d.getTime()) ? null : d;
};

// ✅ Updated utc function
const utc = (t) => {
  const d = toDate(t);
  if (!d) return "Unknown time";
  return d.toISOString().replace("T", " ").replace(".000Z", " UTC");
};

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

const day = (t) => {
  const d = toDate(t);
  if (!d) return "Unknown date";
  return d.toLocaleDateString("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  });
};

const clock = (t) => {
  const d = toDate(t);
  if (!d) return "--:-- UTC";
  return d.toISOString().slice(11, 16) + " UTC";
};

const mins = (a, b) => {
  const ta = Date.parse(a);
  const tb = Date.parse(b);
  if (Number.isNaN(ta) || Number.isNaN(tb)) return 0;
  return Math.max(0, Math.round((tb - ta) / 60000));
};

function describe(e) {
  const x = e.entities || e.attributes || {};
  const inr = e.amount ? "₹" + Number(e.amount).toLocaleString("en-IN") : null;
  switch (e.type) {
    case "UPI":
    case "NEFT":
      return {
        title: inr ?? "Payment",
        meta: `Paid to ${x.payee_id || x.receiver || e.counterparty || "Unknown"}`,
      };
    case "CALL":
      return {
        title: x.direction === "IN" ? "Incoming call" : "Outgoing call",
        meta: `${x.counterparty || e.counterparty || "Unknown"} · ${mins(e.start_utc, e.end_utc)} min`,
      };
    case "IP_SESSION":
      return {
        title: `${mins(e.start_utc, e.end_utc)} min session`,
        meta: `${x.ip || x.public_ip || e.victim_id || "Host"} → ${x.dest_ip || e.counterparty || "Unknown"}`,
      };
    default:
      return {
        title: e.type ? e.type.replaceAll("_", " ") : "Tower ping",
        meta:
          e.geo && e.geo.lat != null && e.geo.lon != null
            ? `Near ${Number(e.geo.lat).toFixed(3)}, ${Number(e.geo.lon).toFixed(3)} (±${e.geo.radius_m ?? 1000} m)`
            : e.latitude != null && e.longitude != null
              ? `Near ${Number(e.latitude).toFixed(3)}, ${Number(e.longitude).toFixed(3)}`
              : e.source_file || "",
      };
  }
}

function Item({ e, side }) {
  const ref = useRef(null);
  const [seen, setSeen] = useState(false);
  useEffect(() => {
    if (!ref.current) return;
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
  const t = TYPES[e.type] ?? { label: e.type || "Event", color: "#94a3b8" };
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

  const normalizedEvents = useMemo(() => {
    const raw = Array.isArray(data?.events) ? data.events : [];
    return raw
      .map((e, idx) => {
        const start = e.start_utc || e.timestamp_utc || e.timestamp || null;
        if (!start) return null;
        return {
          ...e,
          event_id: e.event_id || `evt_${idx}`,
          type: normType(e.type || e.event_type),
          start_utc: String(start),
          end_utc: String(e.end_utc || start),
        };
      })
      .filter(Boolean);
  }, [data]);

  const counts = useMemo(() => {
    const c = {};
    normalizedEvents.forEach((e) => (c[e.type] = (c[e.type] || 0) + 1));
    return c;
  }, [normalizedEvents]);

  const rows = useMemo(() => {
    const list = [...normalizedEvents]
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
  }, [normalizedEvents, on]);

  const toggle = (k) =>
    setOn((s) => {
      const n = new Set(s);
      n.has(k) ? n.delete(k) : n.add(k);
      return n;
    });

  const sessions = (Array.isArray(data?.sessions) ? data.sessions : [])
    .filter(
      (s) =>
        (s.session_type && s.session_type !== "NORMAL") ||
        s.is_long_session ||
        s.is_signature_session ||
        (Array.isArray(s.flags) && s.flags.length > 0),
    )
    .slice(0, 5);

  return (
    <div className="panel neon-card">
      <h2 className="panel-title">Event reconstruction</h2>
      <p className="muted small">
        Case {data?.case_id || "active"} · {rows.filter((r) => r.e).length} of{" "}
        {normalizedEvents.length} events shown
      </p>

      {sessions.map((s, idx) => {
        const sType = String(s.type || s.session_type || "SESSION").replaceAll(
          "_",
          " ",
        );
        const dur =
          s.duration_h ??
          (s.duration_hours != null
            ? Number(s.duration_hours).toFixed(1)
            : "?");
        const flags = Array.isArray(s.flags) ? s.flags : [];
        return (
          <div className="status warn" key={s.session_id || idx}>
            {sType} · {dur} h · {utc(s.start_utc)}
            {flags.length > 0 && (
              <div className="chips">
                {flags.map((f) => (
                  <span key={String(f)}>
                    {String(f || "").replaceAll("_", " ")}
                  </span>
                ))}
              </div>
            )}
          </div>
        );
      })}

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

      {/* ✅ FIX: Wrapped in a scrollable container */}
      <div
        style={{ maxHeight: "58vh", overflowY: "auto", paddingRight: "8px" }}
      >
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
    </div>
  );
}

// ✅ UPDATED: MapView with Fallback logic for event points and geo_tracks points
export function MapView({ data }) {
  const feats = data?.geo_tracks?.[0]?.geojson?.features ?? [];
  const geoPath =
    feats
      .find((f) => f.properties?.kind === "path")
      ?.geometry?.coordinates?.map((c) => [c[1], c[0]]) ?? [];
  const geoPings = feats.filter((f) => f.properties?.kind === "ping");

  // Fallback: plot tower coordinates directly from events (e.g. cdr.csv) & geo_tracks.points
  const eventPts = (data?.events || [])
    .filter((e) => e.latitude != null && e.longitude != null)
    .map((e) => ({
      pos: [Number(e.latitude), Number(e.longitude)],
      label: `${e.event_type || "EVENT"} · ${utc(e.timestamp_utc || e.start_utc)}`,
    }));

  const trackPts = (data?.geo_tracks?.[0]?.points || []).map((p) => ({
    pos: [Number(p.latitude), Number(p.longitude)],
    label: `Tower ${p.tower_id || ""} · ${utc(p.timestamp)}`,
  }));

  const markers = geoPings.length
    ? geoPings.map((p) => ({
        pos: [p.geometry.coordinates[1], p.geometry.coordinates[0]],
        label: utc(p.properties?.time_utc),
      }))
    : trackPts.length
      ? trackPts
      : eventPts;

  const path = geoPath.length ? geoPath : markers.map((m) => m.pos);

  return (
    <div
      className="panel neon-card"
      style={{ padding: 0, overflow: "hidden", height: 560 }}
    >
      <MapContainer
        center={path[0] ?? [28.6139, 77.209]}
        zoom={5}
        style={{ height: "100%", width: "100%", background: "var(--bg-base)" }}
      >
        <TileLayer
          url="https://tile.openstreetmap.org/{z}/{x}/{y}.png"
          attribution="&copy; OpenStreetMap contributors"
        />
        {path.length > 1 && (
          <Polyline
            positions={path}
            pathOptions={{ color: "#22d3ee", weight: 2, opacity: 0.7 }}
          />
        )}
        {markers.map((m, i) => (
          <CircleMarker
            key={i}
            center={m.pos}
            radius={5}
            pathOptions={{
              color: "#f472b6",
              fillColor: "#f472b6",
              fillOpacity: 0.7,
              weight: 1,
            }}
          >
            <Popup>{m.label}</Popup>
          </CircleMarker>
        ))}
      </MapContainer>
    </div>
  );
}
