import { useEffect, useMemo, useRef, useState, useCallback } from "react";
import { Map as MapLibreMap } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";

const INDIA_CENTER = [78.9629, 21.5937];
const INDIA_ZOOM = 4.2;

const INDIA_REGIONS = [
  { state: "Delhi", city: "New Delhi", lat: 28.6139, lon: 77.209 },
  { state: "Maharashtra", city: "Mumbai", lat: 19.076, lon: 72.8777 },
  { state: "Maharashtra", city: "Pune", lat: 18.5204, lon: 73.8567 },
  { state: "Karnataka", city: "Bengaluru", lat: 12.9716, lon: 77.5946 },
  { state: "West Bengal", city: "Kolkata", lat: 22.5726, lon: 88.3639 },
  { state: "Tamil Nadu", city: "Chennai", lat: 13.0827, lon: 80.2707 },
  { state: "Telangana", city: "Hyderabad", lat: 17.385, lon: 78.4867 },
  { state: "Gujarat", city: "Ahmedabad", lat: 23.0225, lon: 72.5714 },
  { state: "Rajasthan", city: "Jaipur", lat: 26.9124, lon: 75.7873 },
  { state: "Uttar Pradesh", city: "Lucknow", lat: 26.8467, lon: 80.9462 },
  { state: "Uttar Pradesh", city: "Noida", lat: 28.5355, lon: 77.391 },
  { state: "Haryana", city: "Gurugram", lat: 28.4595, lon: 77.0266 },
  { state: "Punjab", city: "Chandigarh", lat: 30.7333, lon: 76.7794 },
  { state: "Bihar", city: "Patna", lat: 25.5941, lon: 85.1376 },
  { state: "Madhya Pradesh", city: "Bhopal", lat: 23.2599, lon: 77.4126 },
  { state: "Kerala", city: "Kochi", lat: 9.9312, lon: 76.2673 },
  { state: "Assam", city: "Guwahati", lat: 26.1445, lon: 91.7362 },
];

const EVENT_COLORS = {
  CALL: "#22d3ee",
  IP_SESSION: "#fbbf24",
  TOWER_PING: "#a78bfa",
  UPI: "#f472b6",
  NEFT: "#fb7185",
};

const DEMO_ROUTES_FIXTURE = [
  {
    id: "demo_kol_blr",
    srcState: "West Bengal",
    srcCity: "Kolkata",
    srcLat: 22.5726,
    srcLon: 88.3639,
    dstState: "Karnataka",
    dstCity: "Bengaluru",
    dstLat: 12.9716,
    dstLon: 77.5946,
    count: 45,
    uniqueSuspects: 12,
    categories: ["UPI", "CALL"],
  },
  {
    id: "demo_del_bom",
    srcState: "Delhi",
    srcCity: "New Delhi",
    srcLat: 28.6139,
    srcLon: 77.209,
    dstState: "Maharashtra",
    dstCity: "Mumbai",
    dstLat: 19.076,
    dstLon: 72.8777,
    count: 30,
    uniqueSuspects: 9,
    categories: ["NEFT", "IP_SESSION"],
  },
  {
    id: "demo_kol_del",
    srcState: "West Bengal",
    srcCity: "Kolkata",
    srcLat: 22.5726,
    srcLon: 88.3639,
    dstState: "Delhi",
    dstCity: "New Delhi",
    dstLat: 28.6139,
    dstLon: 77.209,
    count: 20,
    uniqueSuspects: 6,
    categories: ["CALL", "TOWER_PING"],
  },
  {
    id: "demo_hyd_maa",
    srcState: "Telangana",
    srcCity: "Hyderabad",
    srcLat: 17.385,
    srcLon: 78.4867,
    dstState: "Tamil Nadu",
    dstCity: "Chennai",
    dstLat: 13.0827,
    dstLon: 80.2707,
    count: 14,
    uniqueSuspects: 5,
    categories: ["UPI"],
  },
];

function classifyRegion(lat, lon, explicitCity, explicitState) {
  if (explicitCity && explicitState) {
    return { city: explicitCity, state: explicitState };
  }
  let best = INDIA_REGIONS[0];
  let bestD = Infinity;
  for (const r of INDIA_REGIONS) {
    const d = Math.hypot(lat - r.lat, lon - r.lon);
    if (d < bestD) {
      bestD = d;
      best = r;
    }
  }
  return {
    city: explicitCity || best.city,
    state: explicitState || best.state,
  };
}

function makeCurvedArc(lon1, lat1, lon2, lat2, steps = 28) {
  const dx = lon2 - lon1;
  const dy = lat2 - lat1;
  const dist = Math.hypot(dx, dy) || 0.001;
  const cx = (lon1 + lon2) / 2 - (dy / dist) * Math.min(4.5, dist * 0.22);
  const cy = (lat1 + lat2) / 2 + (dx / dist) * Math.min(4.5, dist * 0.22);
  const coords = [];
  for (let i = 0; i <= steps; i++) {
    const t = i / steps;
    const x = (1 - t) * (1 - t) * lon1 + 2 * (1 - t) * t * cx + t * t * lon2;
    const y = (1 - t) * (1 - t) * lat1 + 2 * (1 - t) * t * cy + t * t * lat2;
    coords.push([x, y]);
  }
  return coords;
}

function getLodLevel(z) {
  if (z < 5.3) return 1;
  if (z < 8.5) return 2;
  if (z < 11.5) return 3;
  return 4;
}

function distToSegment(px, py, x1, y1, x2, y2) {
  const dx = x2 - x1;
  const dy = y2 - y1;
  const len2 = dx * dx + dy * dy;
  if (len2 === 0) return Math.hypot(px - x1, py - y1);
  let t = ((px - x1) * dx + (py - y1) * dy) / len2;
  t = Math.max(0, Math.min(1, t));
  return Math.hypot(px - (x1 + t * dx), py - (y1 + t * dy));
}

export default function GeoMap3D({ data }) {
  const mapEl = useRef(null);
  const canvasRef = useRef(null);
  const mapRef = useRef(null);
  const historyRef = useRef([]);
  const stateRef = useRef({});

  const [lod, setLod] = useState(1);
  const [zoomVal, setZoomVal] = useState(INDIA_ZOOM);
  const [is3D, setIs3D] = useState(true);
  const [canGoBack, setCanGoBack] = useState(false);

  const [stateFilter, setStateFilter] = useState("ALL");
  const [typeFilter, setTypeFilter] = useState("ALL");
  const [directionFilter, setDirectionFilter] = useState("ALL");
  const [metricMode, setMetricMode] = useState("relationships");
  const [suspectQuery, setSuspectQuery] = useState("");

  const [selectedLoc, setSelectedLoc] = useState(null);
  const [selectedArc, setSelectedArc] = useState(null);
  const [hoverInfo, setHoverInfo] = useState(null);

  const geoPoints = useMemo(() => {
    const pts = [];
    const seen = new Set();

    const addPt = (raw) => {
      const lat = Number(raw.latitude);
      const lon = Number(raw.longitude);
      if (!Number.isFinite(lat) || !Number.isFinite(lon)) return;
      if (lat < -90 || lat > 90 || lon < -180 || lon > 180) return;
      const { city, state } = classifyRegion(lat, lon, raw.city, raw.state);
      const key = `${raw.id}_${lat.toFixed(4)}_${lon.toFixed(4)}`;
      if (seen.has(key)) return;
      seen.add(key);
      pts.push({
        id: raw.id,
        suspect: String(raw.suspect || "Unknown"),
        counterparty: raw.counterparty ? String(raw.counterparty) : null,
        type: String(raw.type || "TOWER_PING").toUpperCase(),
        timestamp: raw.timestamp || "",
        lat,
        lon,
        city,
        state,
        tower_id: raw.tower_id || null,
      });
    };

    (data?.events || []).forEach((e, idx) => {
      addPt({
        id: e.event_id || `evt_${idx}`,
        suspect: e.victim_id || e.entities?.caller || "Unknown",
        counterparty: e.counterparty || e.entities?.counterparty,
        type: e.type || e.event_type || "TOWER_PING",
        timestamp: e.timestamp_utc || e.start_utc || e.timestamp,
        latitude: e.latitude,
        longitude: e.longitude,
        city: e.city,
        state: e.state,
        tower_id: e.tower_id,
      });
    });

    (data?.geo_tracks || []).forEach((tr, ti) => {
      (tr.points || []).forEach((p, pi) => {
        addPt({
          id: `trk_${ti}_${pi}`,
          suspect: tr.victim_id || "Unknown",
          type: "TOWER_PING",
          timestamp: p.timestamp,
          latitude: p.latitude,
          longitude: p.longitude,
          tower_id: p.tower_id,
        });
      });
    });

    return pts;
  }, [data]);

  const availableStates = useMemo(
    () => ["ALL", ...new Set(geoPoints.map((p) => p.state)).values()].sort(),
    [geoPoints],
  );
  const availableTypes = useMemo(
    () => ["ALL", ...new Set(geoPoints.map((p) => p.type)).values()].sort(),
    [geoPoints],
  );

  const filteredPoints = useMemo(() => {
    const q = suspectQuery.trim().toLowerCase();
    return geoPoints.filter((p) => {
      if (stateFilter !== "ALL" && p.state !== stateFilter) return false;
      if (typeFilter !== "ALL" && p.type !== typeFilter) return false;
      if (
        q &&
        !p.suspect.toLowerCase().includes(q) &&
        !(p.counterparty || "").toLowerCase().includes(q) &&
        !p.city.toLowerCase().includes(q) &&
        !p.state.toLowerCase().includes(q)
      ) {
        return false;
      }
      return true;
    });
  }, [geoPoints, stateFilter, typeFilter, suspectQuery]);

  const rawConnections = useMemo(() => {
    const conns = [];
    const bySuspect = new Map();
    const latestCoordByEntity = new Map();

    for (const p of filteredPoints) {
      if (!bySuspect.has(p.suspect)) bySuspect.set(p.suspect, []);
      bySuspect.get(p.suspect).push(p);
      latestCoordByEntity.set(p.suspect, p);
    }

    for (const [suspect, list] of bySuspect) {
      const sorted = [...list].sort((a, b) =>
        String(a.timestamp).localeCompare(String(b.timestamp)),
      );
      for (let i = 0; i < sorted.length - 1; i++) {
        const a = sorted[i];
        const b = sorted[i + 1];
        if (a.lat === b.lat && a.lon === b.lon) continue;
        conns.push({
          id: `mov_${a.id}_${b.id}`,
          source: a,
          target: b,
          suspect,
          category: b.type,
          timestamp: b.timestamp,
        });
      }
    }

    for (const p of filteredPoints) {
      if (!p.counterparty) continue;
      const targetPt = latestCoordByEntity.get(p.counterparty);
      if (!targetPt || (targetPt.lat === p.lat && targetPt.lon === p.lon))
        continue;
      conns.push({
        id: `rel_${p.id}_${targetPt.id}`,
        source: p,
        target: targetPt,
        suspect: p.suspect,
        counterparty: p.counterparty,
        category: p.type,
        timestamp: p.timestamp,
      });
    }

    return conns;
  }, [filteredPoints]);

  const aggregated = useMemo(() => {
    const scope = lod === 1 ? "state" : "city";
    const hubs = new Map();

    for (const p of filteredPoints) {
      const key = scope === "state" ? p.state : `${p.city}, ${p.state}`;
      if (!hubs.has(key)) {
        hubs.set(key, {
          key,
          name: scope === "state" ? p.state : p.city,
          state: p.state,
          latSum: 0,
          lonSum: 0,
          count: 0,
          suspects: new Set(),
          inCount: 0,
          outCount: 0,
          connectedLocs: new Set(),
        });
      }
      const h = hubs.get(key);
      h.latSum += p.lat;
      h.lonSum += p.lon;
      h.count++;
      h.suspects.add(p.suspect);
    }

    const routes = new Map();
    for (const c of rawConnections) {
      const srcKey =
        scope === "state"
          ? c.source.state
          : `${c.source.city}, ${c.source.state}`;
      const dstKey =
        scope === "state"
          ? c.target.state
          : `${c.target.city}, ${c.target.state}`;
      if (srcKey === dstKey) continue;

      if (selectedLoc) {
        if (directionFilter === "IN" && dstKey !== selectedLoc.key) continue;
        if (directionFilter === "OUT" && srcKey !== selectedLoc.key) continue;
      }

      const sh = hubs.get(srcKey);
      const dh = hubs.get(dstKey);
      if (sh && dh) {
        sh.outCount++;
        dh.inCount++;
        sh.connectedLocs.add(dstKey);
        dh.connectedLocs.add(srcKey);
      }

      const rKey = `${srcKey}→${dstKey}`;
      if (!routes.has(rKey)) {
        routes.set(rKey, {
          id: rKey,
          srcKey,
          dstKey,
          srcName: sh?.name || srcKey,
          dstName: dh?.name || dstKey,
          suspects: new Set(),
          categories: new Set(),
          items: [],
        });
      }
      const r = routes.get(rKey);
      r.suspects.add(c.suspect);
      r.categories.add(c.category);
      r.items.push(c);
    }

    const hubList = [...hubs.values()].map((h) => {
      const lat = h.latSum / h.count;
      const lon = h.lonSum / h.count;
      const metricVal =
        metricMode === "suspects"
          ? h.suspects.size
          : metricMode === "activity"
            ? h.count
            : h.inCount + h.outCount;
      return {
        ...h,
        lat,
        lon,
        suspectCount: h.suspects.size,
        metricVal,
        connectedList: [...h.connectedLocs],
      };
    });

    const routeList = [...routes.values()].map((r) => {
      const sh = hubs.get(r.srcKey);
      const dh = hubs.get(r.dstKey);
      const sLat = sh.latSum / sh.count;
      const sLon = sh.lonSum / sh.count;
      const dLat = dh.latSum / dh.count;
      const dLon = dh.lonSum / dh.count;
      return {
        ...r,
        count: r.items.length,
        uniqueSuspects: r.suspects.size,
        suspectList: [...r.suspects],
        categoryList: [...r.categories],
        coords: makeCurvedArc(sLon, sLat, dLon, dLat),
      };
    });

    let isDemoRoutes = false;
    if (routeList.length === 0) {
      isDemoRoutes = true;
      const demoHubMap = new Map();
      for (const dr of DEMO_ROUTES_FIXTURE) {
        const srcKey =
          scope === "state" ? dr.srcState : `${dr.srcCity}, ${dr.srcState}`;
        const dstKey =
          scope === "state" ? dr.dstState : `${dr.dstCity}, ${dr.dstState}`;

        if (!demoHubMap.has(srcKey)) {
          demoHubMap.set(srcKey, {
            key: srcKey,
            name: scope === "state" ? dr.srcState : dr.srcCity,
            state: dr.srcState,
            lat: dr.srcLat,
            lon: dr.srcLon,
            count: dr.count,
            suspectCount: dr.uniqueSuspects,
            metricVal: dr.count,
            inCount: 0,
            outCount: dr.count,
            connectedList: [dstKey],
          });
        }
        if (!demoHubMap.has(dstKey)) {
          demoHubMap.set(dstKey, {
            key: dstKey,
            name: scope === "state" ? dr.dstState : dr.dstCity,
            state: dr.dstState,
            lat: dr.dstLat,
            lon: dr.dstLon,
            count: dr.count,
            suspectCount: dr.uniqueSuspects,
            metricVal: dr.count,
            inCount: dr.count,
            outCount: 0,
            connectedList: [srcKey],
          });
        }

        routeList.push({
          id: dr.id,
          srcKey,
          dstKey,
          srcName: scope === "state" ? dr.srcState : dr.srcCity,
          dstName: scope === "state" ? dr.dstState : dr.dstCity,
          count: dr.count,
          uniqueSuspects: dr.uniqueSuspects,
          suspectList: ["Demo Fixture"],
          categoryList: dr.categories,
          coords: makeCurvedArc(dr.srcLon, dr.srcLat, dr.dstLon, dr.dstLat),
          items: [
            {
              id: dr.id + "_sample",
              suspect: "Demo Route (no backend geo-links)",
              counterparty: `${dr.srcCity} → ${dr.dstCity}`,
              category: dr.categories.join(", "),
              timestamp: "Demo fixture",
            },
          ],
        });
      }
      if (hubList.length === 0) {
        hubList.push(...demoHubMap.values());
      }
    }

    return { hubList, routeList, isDemoRoutes };
  }, [
    filteredPoints,
    rawConnections,
    lod,
    metricMode,
    selectedLoc,
    directionFilter,
  ]);

  stateRef.current = {
    aggregated,
    filteredPoints,
    lod,
    selectedLoc,
    selectedArc,
    is3D,
  };

  const drawOverlay = useCallback(() => {
    const map = mapRef.current;
    const canvas = canvasRef.current;
    if (!map || !canvas) return;

    const w = canvas.clientWidth;
    const h = canvas.clientHeight;
    if (!w || !h) return;

    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    if (
      canvas.width !== Math.round(w * dpr) ||
      canvas.height !== Math.round(h * dpr)
    ) {
      canvas.width = Math.round(w * dpr);
      canvas.height = Math.round(h * dpr);
    }

    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);

    const {
      aggregated: agg,
      filteredPoints: pts,
      lod: curLod,
      selectedLoc: selLoc,
      selectedArc: selArc,
      is3D: tilt3D,
    } = stateRef.current;

    if (!agg) return;

    for (const r of agg.routeList) {
      const touchesSel =
        selLoc && (r.srcKey === selLoc.key || r.dstKey === selLoc.key);
      const isSelected = selArc && selArc.id === r.id;
      const dimmed = !!selLoc && !touchesSel;

      const screenPts = r.coords.map((c) => map.project(c));
      if (screenPts.length < 2) continue;

      const start = screenPts[0];
      const end = screenPts[screenPts.length - 1];
      const pxDist = Math.hypot(end.x - start.x, end.y - start.y);
      const maxLift = tilt3D ? Math.min(44, pxDist * 0.16) : 0;

      const lifted = screenPts.map((pt, idx) => {
        const t = idx / (screenPts.length - 1);
        return { x: pt.x, y: pt.y - Math.sin(t * Math.PI) * maxLift };
      });

      ctx.save();
      ctx.beginPath();
      ctx.moveTo(lifted[0].x, lifted[0].y);
      for (let i = 1; i < lifted.length; i++) {
        ctx.lineTo(lifted[i].x, lifted[i].y);
      }
      ctx.lineCap = "round";
      ctx.lineJoin = "round";
      ctx.strokeStyle = isSelected || touchesSel ? "#22d3ee" : "#f472b6";
      ctx.globalAlpha = dimmed ? 0.18 : 0.9;
      ctx.lineWidth = Math.min(6.5, 1.8 + Math.log2(r.count + 1) * 1.15);
      ctx.shadowColor = isSelected || touchesSel ? "#22d3ee" : "#f472b6";
      ctx.shadowBlur = dimmed ? 0 : 10;
      ctx.stroke();

      const midIdx = Math.floor(lifted.length * 0.55);
      const p1 = lifted[Math.max(0, midIdx - 1)];
      const p2 = lifted[midIdx];
      const ang = Math.atan2(p2.y - p1.y, p2.x - p1.x);
      ctx.fillStyle = isSelected || touchesSel ? "#22d3ee" : "#f472b6";
      ctx.beginPath();
      ctx.moveTo(p2.x + Math.cos(ang) * 5, p2.y + Math.sin(ang) * 5);
      ctx.lineTo(
        p2.x - Math.cos(ang - 0.55) * 8,
        p2.y - Math.sin(ang - 0.55) * 8,
      );
      ctx.lineTo(
        p2.x - Math.cos(ang + 0.55) * 8,
        p2.y - Math.sin(ang + 0.55) * 8,
      );
      ctx.closePath();
      ctx.fill();
      ctx.restore();
    }

    if (curLod <= 2) {
      for (const hub of agg.hubList) {
        const pt = map.project([hub.lon, hub.lat]);
        const dimmed =
          !!selLoc &&
          selLoc.key !== hub.key &&
          !selLoc.connectedList.includes(hub.key);

        const col = dimmed ? "#475569" : "#22d3ee";
        const pillarH = tilt3D
          ? Math.min(82, Math.max(14, hub.metricVal * 1.35))
          : 0;
        const r = Math.min(13, 6 + Math.sqrt(Math.max(1, hub.metricVal)) * 1.2);

        ctx.save();
        ctx.globalAlpha = dimmed ? 0.32 : 0.92;

        if (pillarH > 0) {
          const grad = ctx.createLinearGradient(
            pt.x,
            pt.y - pillarH,
            pt.x,
            pt.y,
          );
          grad.addColorStop(0, col);
          grad.addColorStop(1, "rgba(34, 211, 238, 0.12)");
          ctx.fillStyle = grad;
          ctx.fillRect(pt.x - 5, pt.y - pillarH, 10, pillarH);
          ctx.strokeStyle = col;
          ctx.lineWidth = 1;
          ctx.strokeRect(pt.x - 5, pt.y - pillarH, 10, pillarH);
        }

        ctx.beginPath();
        ctx.arc(pt.x, pt.y - pillarH, r * 0.65, 0, Math.PI * 2);
        ctx.fillStyle = col;
        ctx.shadowColor = col;
        ctx.shadowBlur = dimmed ? 0 : 12;
        ctx.fill();
        ctx.lineWidth = 2;
        ctx.strokeStyle = "#090e1c";
        ctx.stroke();

        const label = `${hub.name} (${hub.metricVal})`;
        ctx.shadowBlur = 0;
        ctx.font = "600 11px ui-sans-serif, system-ui, sans-serif";
        ctx.textAlign = "center";
        ctx.lineWidth = 3;
        ctx.strokeStyle = "#090e1c";
        ctx.strokeText(label, pt.x, pt.y - pillarH - r * 0.65 - 6);
        ctx.fillStyle = "#e2e8f0";
        ctx.fillText(label, pt.x, pt.y - pillarH - r * 0.65 - 6);
        ctx.restore();
      }
    } else {
      for (const p of pts) {
        const pt = map.project([p.lon, p.lat]);
        ctx.save();
        ctx.beginPath();
        ctx.arc(pt.x, pt.y, 5.5, 0, Math.PI * 2);
        ctx.fillStyle = EVENT_COLORS[p.type] || "#f472b6";
        ctx.fill();
        ctx.lineWidth = 1.5;
        ctx.strokeStyle = "#ffffff";
        ctx.stroke();
        ctx.restore();
      }
    }
  }, []);

  const pushCamHistory = useCallback(() => {
    const map = mapRef.current;
    if (!map) return;
    historyRef.current.push({
      center: map.getCenter(),
      zoom: map.getZoom(),
      pitch: map.getPitch(),
      bearing: map.getBearing(),
    });
    if (historyRef.current.length > 12) historyRef.current.shift();
    setCanGoBack(true);
  }, []);

  useEffect(() => {
    if (!mapEl.current || mapRef.current) return;

    const map = new MapLibreMap({
      container: mapEl.current,
      style: {
        version: 8,
        sources: {
          "osm-dark": {
            type: "raster",
            tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
            tileSize: 256,
            attribution: "&copy; OpenStreetMap contributors",
          },
        },
        layers: [
          {
            id: "osm-dark-layer",
            type: "raster",
            source: "osm-dark",
            paint: {
              "raster-brightness-max": 0.42,
              "raster-saturation": -0.75,
              "raster-contrast": 0.25,
            },
          },
        ],
      },
      center: INDIA_CENTER,
      zoom: INDIA_ZOOM,
      pitch: 42,
      bearing: -10,
      maxPitch: 65,
    });

    mapRef.current = map;

    const hitTest = (px, py) => {
      const { aggregated: agg, lod: curLod, is3D: tilt3D } = stateRef.current;
      if (!agg) return null;

      if (curLod <= 2) {
        for (const hub of agg.hubList) {
          const pt = map.project([hub.lon, hub.lat]);
          const pillarH = tilt3D
            ? Math.min(82, Math.max(14, hub.metricVal * 1.35))
            : 0;
          if (
            Math.hypot(px - pt.x, py - pt.y) < 16 ||
            Math.hypot(px - pt.x, py - (pt.y - pillarH)) < 16
          ) {
            return { kind: "hub", item: hub };
          }
        }
      }

      for (const r of agg.routeList) {
        const screenPts = r.coords.map((c) => map.project(c));
        if (screenPts.length < 2) continue;
        const start = screenPts[0];
        const end = screenPts[screenPts.length - 1];
        const pxDist = Math.hypot(end.x - start.x, end.y - start.y);
        const maxLift = tilt3D ? Math.min(44, pxDist * 0.16) : 0;
        const lifted = screenPts.map((pt, idx) => {
          const t = idx / (screenPts.length - 1);
          return { x: pt.x, y: pt.y - Math.sin(t * Math.PI) * maxLift };
        });
        for (let i = 0; i < lifted.length - 1; i++) {
          if (
            distToSegment(
              px,
              py,
              lifted[i].x,
              lifted[i].y,
              lifted[i + 1].x,
              lifted[i + 1].y,
            ) < 10
          ) {
            return { kind: "arc", item: r };
          }
        }
      }
      return null;
    };

    map.on("style.load", drawOverlay);
    map.on("render", drawOverlay);
    map.on("move", () => {
      setHoverInfo(null);
      drawOverlay();
    });
    map.on("resize", drawOverlay);

    map.on("zoomend", () => {
      const z = map.getZoom();
      setZoomVal(Number(z.toFixed(1)));
      setLod(getLodLevel(z));
    });

    map.on("mousemove", (e) => {
      const hit = hitTest(e.point.x, e.point.y);
      if (!hit) {
        map.getCanvas().style.cursor = "";
        setHoverInfo(null);
        return;
      }
      map.getCanvas().style.cursor = "pointer";
      setHoverInfo({
        x: e.point.x,
        y: e.point.y,
        kind: hit.kind,
        item: hit.item,
      });
    });

    map.on("mouseout", () => setHoverInfo(null));

    map.on("click", (e) => {
      const hit = hitTest(e.point.x, e.point.y);
      if (!hit) return;
      if (hit.kind === "hub") {
        setSelectedLoc(hit.item);
        setSelectedArc(null);
      } else if (hit.kind === "arc") {
        setSelectedArc(hit.item);
        setSelectedLoc(null);
      }
    });

    return () => {
      map.remove();
      mapRef.current = null;
    };
  }, [drawOverlay]);

  useEffect(() => {
    drawOverlay();
  }, [
    aggregated,
    filteredPoints,
    lod,
    selectedLoc,
    selectedArc,
    is3D,
    drawOverlay,
  ]);

  const flyTo = (opts) => {
    pushCamHistory();
    mapRef.current?.flyTo({ duration: 650, ...opts });
  };

  const goBack = () => {
    const prev = historyRef.current.pop();
    setCanGoBack(historyRef.current.length > 0);
    if (prev) mapRef.current?.flyTo({ duration: 550, ...prev });
  };

  const toggle3D = () => {
    const next = !is3D;
    setIs3D(next);
    mapRef.current?.easeTo({ pitch: next ? 42 : 0, duration: 450 });
  };

  const lodName =
    lod === 1
      ? "L1 · Country (States)"
      : lod === 2
        ? "L2 · State (Cities)"
        : lod === 3
          ? "L3 · City (Clusters)"
          : "L4 · Individual Points";

  return (
    <div className="panel neon-card">
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          flexWrap: "wrap",
          gap: 10,
          marginBottom: 10,
        }}
      >
        <div>
          <h2 className="panel-title">3D Geospatial Investigation Map</h2>
          <p className="muted small">
            {filteredPoints.length} geo events · {aggregated.routeList.length}{" "}
            aggregated routes ·{" "}
            <span style={{ color: "#22d3ee" }}>{lodName}</span> ({zoomVal}x)
            {aggregated.isDemoRoutes && (
              <span style={{ color: "#fbbf24", marginLeft: 8 }}>
                · Demo Arcs (no backend routes)
              </span>
            )}
          </p>
        </div>

        <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
          <input
            value={suspectQuery}
            onChange={(e) => setSuspectQuery(e.target.value)}
            placeholder="Filter suspect / city..."
            style={{
              padding: "5px 9px",
              borderRadius: 6,
              border: "1px solid var(--border-strong)",
              background: "var(--bg-base)",
              color: "inherit",
              fontSize: 12,
            }}
          />
          <select
            value={stateFilter}
            onChange={(e) => setStateFilter(e.target.value)}
            style={{
              padding: "5px 8px",
              borderRadius: 6,
              border: "1px solid var(--border-strong)",
              background: "var(--bg-base)",
              color: "inherit",
              fontSize: 12,
            }}
          >
            {availableStates.map((s) => (
              <option key={s} value={s}>
                {s === "ALL" ? "All States" : s}
              </option>
            ))}
          </select>
          <select
            value={typeFilter}
            onChange={(e) => setTypeFilter(e.target.value)}
            style={{
              padding: "5px 8px",
              borderRadius: 6,
              border: "1px solid var(--border-strong)",
              background: "var(--bg-base)",
              color: "inherit",
              fontSize: 12,
            }}
          >
            {availableTypes.map((t) => (
              <option key={t} value={t}>
                {t === "ALL" ? "All Types" : t}
              </option>
            ))}
          </select>
          <select
            value={metricMode}
            onChange={(e) => setMetricMode(e.target.value)}
            title="3D Pillar Height Metric"
            style={{
              padding: "5px 8px",
              borderRadius: 6,
              border: "1px solid var(--border-strong)",
              background: "var(--bg-base)",
              color: "inherit",
              fontSize: 12,
            }}
          >
            <option value="relationships">Metric: Connections</option>
            <option value="suspects">Metric: Unique Suspects</option>
            <option value="activity">Metric: Activity Events</option>
          </select>
        </div>
      </div>

      <div
        style={{
          position: "relative",
          height: 580,
          borderRadius: 10,
          overflow: "hidden",
          border: "1px solid var(--border-subtle)",
        }}
      >
        <div ref={mapEl} style={{ width: "100%", height: "100%" }} />
        <canvas
          ref={canvasRef}
          style={{
            position: "absolute",
            inset: 0,
            width: "100%",
            height: "100%",
            pointerEvents: "none",
            zIndex: 2,
          }}
        />

        {hoverInfo && (
          <div
            style={{
              position: "absolute",
              left: Math.min(
                hoverInfo.x + 14,
                (mapEl.current?.clientWidth || 700) - 260,
              ),
              top: Math.max(12, hoverInfo.y - 16),
              transform: "translateY(-100%)",
              zIndex: 25,
              pointerEvents: "none",
              minWidth: 210,
              maxWidth: 260,
              padding: "10px 12px",
              borderRadius: 8,
              background: "rgba(6, 10, 20, 0.96)",
              border:
                hoverInfo.kind === "arc"
                  ? "1px solid rgba(244, 114, 182, 0.55)"
                  : "1px solid rgba(34, 211, 238, 0.55)",
              boxShadow: "0 10px 26px rgba(0, 0, 0, 0.75)",
              color: "#e2e8f0",
              fontSize: 12,
              lineHeight: 1.45,
            }}
          >
            {hoverInfo.kind === "hub" ? (
              <>
                <div
                  style={{ color: "#22d3ee", fontWeight: 700, fontSize: 13 }}
                >
                  {hoverInfo.item.name}
                  {hoverInfo.item.state !== hoverInfo.item.name
                    ? `, ${hoverInfo.item.state}`
                    : ""}
                </div>
                <div style={{ marginTop: 4 }}>
                  <b>{hoverInfo.item.suspectCount}</b> suspect(s) ·{" "}
                  <b>{hoverInfo.item.count}</b> activity events
                </div>
                <div style={{ color: "#94a3b8", fontSize: 11 }}>
                  In: {hoverInfo.item.inCount} · Out: {hoverInfo.item.outCount}{" "}
                  · {hoverInfo.item.connectedList.length} linked hub(s)
                </div>
                {hoverInfo.item.connectedList.length > 0 && (
                  <div style={{ color: "#cbd5e1", fontSize: 11, marginTop: 3 }}>
                    Links: {hoverInfo.item.connectedList.slice(0, 4).join(", ")}
                    {hoverInfo.item.connectedList.length > 4 ? "…" : ""}
                  </div>
                )}
              </>
            ) : (
              <>
                <div
                  style={{ color: "#f472b6", fontWeight: 700, fontSize: 13 }}
                >
                  {hoverInfo.item.srcName} → {hoverInfo.item.dstName}
                </div>
                <div style={{ marginTop: 4 }}>
                  <b>{hoverInfo.item.count}</b> connections ·{" "}
                  <b>{hoverInfo.item.uniqueSuspects}</b> suspect(s)
                </div>
                <div style={{ color: "#22d3ee", fontSize: 11 }}>
                  {hoverInfo.item.categoryList.join(", ")}
                </div>
                {hoverInfo.item.suspectList?.length > 0 && (
                  <div style={{ color: "#94a3b8", fontSize: 11, marginTop: 3 }}>
                    Entities:{" "}
                    {hoverInfo.item.suspectList.slice(0, 3).join(", ")}
                    {hoverInfo.item.suspectList.length > 3 ? "…" : ""}
                  </div>
                )}
              </>
            )}
          </div>
        )}

        <div
          style={{
            position: "absolute",
            top: 12,
            left: 12,
            zIndex: 5,
            display: "flex",
            gap: 6,
            flexWrap: "wrap",
            background: "rgba(9, 14, 28, 0.88)",
            padding: "6px 10px",
            borderRadius: 8,
            border: "1px solid rgba(34,211,238,0.28)",
          }}
        >
          <button
            className="mini"
            onClick={() =>
              flyTo({
                zoom: Math.min(15, (mapRef.current?.getZoom() || 4) + 1.5),
              })
            }
          >
            +
          </button>
          <button
            className="mini"
            onClick={() =>
              flyTo({
                zoom: Math.max(2, (mapRef.current?.getZoom() || 4) - 1.5),
              })
            }
          >
            −
          </button>
          <button className="mini" onClick={toggle3D}>
            {is3D ? "2D Flat" : "3D Tilt"}
          </button>
          <button
            className="mini"
            onClick={() =>
              flyTo({ bearing: (mapRef.current?.getBearing() || 0) - 25 })
            }
            title="Rotate Left"
          >
            ⟲
          </button>
          <button
            className="mini"
            onClick={() =>
              flyTo({ bearing: (mapRef.current?.getBearing() || 0) + 25 })
            }
            title="Rotate Right"
          >
            ⟳
          </button>
          {canGoBack && (
            <button className="mini" onClick={goBack}>
              ← Back
            </button>
          )}
          <button
            className="mini"
            onClick={() => {
              setSelectedLoc(null);
              setSelectedArc(null);
              flyTo({
                center: INDIA_CENTER,
                zoom: INDIA_ZOOM,
                pitch: is3D ? 42 : 0,
                bearing: -10,
              });
            }}
          >
            Reset India
          </button>
        </div>

        {selectedLoc && (
          <div
            className="node-card"
            style={{
              position: "absolute",
              top: 12,
              right: 12,
              width: 310,
              maxHeight: "calc(100% - 24px)",
              overflowY: "auto",
              zIndex: 8,
              background: "rgba(9, 14, 28, 0.94)",
              border: "1px solid rgba(34,211,238,0.35)",
            }}
          >
            <button
              className="x"
              onClick={() => setSelectedLoc(null)}
              aria-label="Close"
            >
              ×
            </button>
            <div className="nc-role" style={{ color: "#22d3ee" }}>
              {lod === 1 ? "State Hub" : "City Hub"}
            </div>
            <h3>{selectedLoc.name}</h3>
            <dl style={{ fontSize: 12 }}>
              <dt>Unique Suspects</dt>
              <dd>{selectedLoc.suspectCount}</dd>
              <dt>Activity Events</dt>
              <dd>{selectedLoc.count}</dd>
              <dt>Incoming Routes</dt>
              <dd>{selectedLoc.inCount}</dd>
              <dt>Outgoing Routes</dt>
              <dd>{selectedLoc.outCount}</dd>
              <dt>Connected Locations</dt>
              <dd>{selectedLoc.connectedList.length}</dd>
            </dl>
            <div style={{ display: "flex", gap: 6, marginBottom: 8 }}>
              {["ALL", "IN", "OUT"].map((d) => (
                <button
                  key={d}
                  className={"mini" + (directionFilter === d ? " on" : "")}
                  onClick={() => setDirectionFilter(d)}
                >
                  {d}
                </button>
              ))}
              <button
                className="mini"
                onClick={() =>
                  flyTo({
                    center: [selectedLoc.lon, selectedLoc.lat],
                    zoom: lod === 1 ? 6.5 : 10,
                  })
                }
              >
                Zoom In
              </button>
            </div>
            {selectedLoc.connectedList.length > 0 && (
              <div className="small muted">
                Related: {selectedLoc.connectedList.join(", ")}
              </div>
            )}
          </div>
        )}

        {selectedArc && (
          <div
            className="node-card"
            style={{
              position: "absolute",
              top: 12,
              right: 12,
              width: 330,
              maxHeight: "calc(100% - 24px)",
              overflowY: "auto",
              zIndex: 8,
              background: "rgba(9, 14, 28, 0.94)",
              border: "1px solid rgba(244,114,182,0.4)",
            }}
          >
            <button
              className="x"
              onClick={() => setSelectedArc(null)}
              aria-label="Close"
            >
              ×
            </button>
            <div className="nc-role" style={{ color: "#f472b6" }}>
              Aggregated Route
            </div>
            <h3>
              {selectedArc.srcName} → {selectedArc.dstName}
            </h3>
            <p className="small muted">
              {selectedArc.count} relationships · {selectedArc.uniqueSuspects}{" "}
              unique suspect(s) · {selectedArc.categoryList.join(", ")}
            </p>
            <div style={{ display: "grid", gap: 6, fontSize: 12 }}>
              {selectedArc.items.slice(0, 25).map((item) => (
                <div
                  key={item.id}
                  style={{
                    padding: "6px 8px",
                    borderRadius: 6,
                    background: "var(--bg-base)",
                    border: "1px solid var(--border-subtle)",
                  }}
                >
                  <b>{item.suspect}</b>
                  {item.counterparty ? ` ↔ ${item.counterparty}` : ""} ·{" "}
                  <span style={{ color: "#22d3ee" }}>{item.category}</span>
                  <div className="mono muted" style={{ fontSize: 10 }}>
                    {item.timestamp}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      <p className="muted small" style={{ marginTop: 8 }}>
        <b>Legend:</b> 3D cyan pillar height = selected metric (Connections /
        Unique Suspects / Activity) · Pink curved arc thickness = aggregated
        relationship count (<code>log2</code>). Trackpad: Two-finger scroll =
        Zoom · Drag = Pan · <code>Ctrl</code>+Drag or <code>⟲ / ⟳</code> =
        Rotate.
      </p>
    </div>
  );
}
