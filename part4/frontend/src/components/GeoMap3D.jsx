import { useEffect, useMemo, useRef, useState, useCallback } from "react";
import { Map as MapLibreMap, Popup as MapPopup } from "maplibre-gl";
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

function makeCurvedArc(lon1, lat1, lon2, lat2, steps = 24) {
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

function makeHexPolygon(lon, lat, radiusDeg = 0.28) {
  const pts = [];
  for (let i = 0; i < 6; i++) {
    const a = (Math.PI / 3) * i;
    pts.push([lon + Math.cos(a) * radiusDeg, lat + Math.sin(a) * radiusDeg]);
  }
  pts.push(pts[0]);
  return [pts];
}

function getLodLevel(z) {
  if (z < 5.3) return 1;
  if (z < 8.5) return 2;
  if (z < 11.5) return 3;
  return 4;
}

export default function GeoMap3D({ data }) {
  const mapEl = useRef(null);
  const mapRef = useRef(null);
  const popupRef = useRef(null);
  const historyRef = useRef([]);

  const [lod, setLod] = useState(1);
  const [zoomVal, setZoomVal] = useState(INDIA_ZOOM);
  const [is3D, setIs3D] = useState(true);
  const [canGoBack, setCanGoBack] = useState(false);
  const [mapReady, setMapReady] = useState(false);

  const [stateFilter, setStateFilter] = useState("ALL");
  const [typeFilter, setTypeFilter] = useState("ALL");
  const [directionFilter, setDirectionFilter] = useState("ALL");
  const [metricMode, setMetricMode] = useState("relationships");
  const [suspectQuery, setSuspectQuery] = useState("");

  const [selectedLoc, setSelectedLoc] = useState(null);
  const [selectedArc, setSelectedArc] = useState(null);

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
        categoryList: [...r.categories],
        coords: makeCurvedArc(sLon, sLat, dLon, dLat),
      };
    });

    return { hubList, routeList };
  }, [
    filteredPoints,
    rawConnections,
    lod,
    metricMode,
    selectedLoc,
    directionFilter,
  ]);

  useEffect(() => {
    if (!mapEl.current || mapRef.current) return;

    const map = new MapLibreMap({
      container: mapEl.current,
      style: {
        version: 8,
        glyphs: "https://demotiles.maplibre.org/font/{fontstack}/{range}.pbf",
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
    popupRef.current = new MapPopup({
      closeButton: false,
      closeOnClick: false,
    });

    map.on("load", () => {
      map.addSource("hub-pillars", {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] },
      });
      map.addSource("hub-points", {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] },
      });
      map.addSource("agg-arcs", {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] },
      });
      map.addSource("ind-points", {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] },
        cluster: true,
        clusterMaxZoom: 11,
        clusterRadius: 42,
      });

      map.addLayer({
        id: "hub-pillars-3d",
        type: "fill-extrusion",
        source: "hub-pillars",
        paint: {
          "fill-extrusion-color": [
            "case",
            ["boolean", ["get", "dimmed"], false],
            "#334155",
            "#22d3ee",
          ],
          "fill-extrusion-height": ["get", "height"],
          "fill-extrusion-base": 0,
          "fill-extrusion-opacity": 0.58,
        },
      });

      map.addLayer({
        id: "agg-arcs-layer",
        type: "line",
        source: "agg-arcs",
        layout: { "line-cap": "round", "line-join": "round" },
        paint: {
          "line-color": [
            "case",
            ["boolean", ["get", "highlighted"], false],
            "#38bdf8",
            ["boolean", ["get", "dimmed"], false],
            "rgba(100,116,139,0.18)",
            "#f472b6",
          ],
          "line-width": ["get", "width"],
          "line-opacity": [
            "case",
            ["boolean", ["get", "dimmed"], false],
            0.2,
            0.88,
          ],
        },
      });

      map.addLayer({
        id: "hub-points-layer",
        type: "circle",
        source: "hub-points",
        paint: {
          "circle-radius": ["get", "radius"],
          "circle-color": [
            "case",
            ["boolean", ["get", "dimmed"], false],
            "#475569",
            "#22d3ee",
          ],
          "circle-stroke-width": 2,
          "circle-stroke-color": "#090e1c",
        },
      });

      map.addLayer({
        id: "hub-labels-layer",
        type: "symbol",
        source: "hub-points",
        layout: {
          "text-field": ["get", "label"],
          "text-size": 11,
          "text-offset": [0, 1.5],
          "text-anchor": "top",
        },
        paint: {
          "text-color": "#e2e8f0",
          "text-halo-color": "#090e1c",
          "text-halo-width": 1.5,
        },
      });

      map.addLayer({
        id: "clusters-layer",
        type: "circle",
        source: "ind-points",
        filter: ["has", "point_count"],
        paint: {
          "circle-color": "#38bdf8",
          "circle-radius": [
            "step",
            ["get", "point_count"],
            16,
            25,
            22,
            100,
            28,
          ],
          "circle-opacity": 0.85,
          "circle-stroke-width": 2,
          "circle-stroke-color": "#090e1c",
        },
      });

      map.addLayer({
        id: "cluster-count-layer",
        type: "symbol",
        source: "ind-points",
        filter: ["has", "point_count"],
        layout: {
          "text-field": "{point_count_abbreviated}",
          "text-size": 12,
        },
        paint: { "text-color": "#090e1c" },
      });

      map.addLayer({
        id: "unclustered-points-layer",
        type: "circle",
        source: "ind-points",
        filter: ["!", ["has", "point_count"]],
        paint: {
          "circle-color": ["get", "color"],
          "circle-radius": 6,
          "circle-stroke-width": 1.5,
          "circle-stroke-color": "#ffffff",
        },
      });

      setZoomVal(Number(map.getZoom().toFixed(1)));
      setLod(getLodLevel(map.getZoom()));
      setMapReady(true);
    });

    map.on("zoomend", () => {
      const z = map.getZoom();
      setZoomVal(Number(z.toFixed(1)));
      setLod(getLodLevel(z));
    });

    return () => {
      map.remove();
      mapRef.current = null;
      setMapReady(false);
    };
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady) return;

    const showHubs = lod <= 2;
    const pillarRadius = lod === 1 ? 0.38 : 0.16;

    const pillarFeatures = showHubs
      ? aggregated.hubList.map((h) => ({
          type: "Feature",
          properties: {
            key: h.key,
            height: Math.min(280000, Math.max(20000, h.metricVal * 4200)),
            dimmed:
              !!selectedLoc &&
              selectedLoc.key !== h.key &&
              !selectedLoc.connectedList.includes(h.key),
          },
          geometry: {
            type: "Polygon",
            coordinates: makeHexPolygon(h.lon, h.lat, pillarRadius),
          },
        }))
      : [];

    const hubFeatures = showHubs
      ? aggregated.hubList.map((h) => ({
          type: "Feature",
          properties: {
            key: h.key,
            label: `${h.name} (${h.metricVal})`,
            radius: Math.min(18, 7 + Math.sqrt(h.metricVal) * 1.4),
            dimmed:
              !!selectedLoc &&
              selectedLoc.key !== h.key &&
              !selectedLoc.connectedList.includes(h.key),
          },
          geometry: { type: "Point", coordinates: [h.lon, h.lat] },
        }))
      : [];

    const arcFeatures = aggregated.routeList.map((r) => {
      const touchesSel =
        selectedLoc &&
        (r.srcKey === selectedLoc.key || r.dstKey === selectedLoc.key);
      return {
        type: "Feature",
        properties: {
          id: r.id,
          srcName: r.srcName,
          dstName: r.dstName,
          count: r.count,
          uniqueSuspects: r.uniqueSuspects,
          categories: r.categoryList.join(", "),
          width: Math.min(7, 1.5 + Math.log2(r.count + 1) * 1.2),
          highlighted: !!touchesSel,
          dimmed: !!selectedLoc && !touchesSel,
        },
        geometry: { type: "LineString", coordinates: r.coords },
      };
    });

    const indFeatures =
      lod >= 3
        ? filteredPoints.map((p) => ({
            type: "Feature",
            properties: {
              id: p.id,
              suspect: p.suspect,
              type: p.type,
              city: p.city,
              state: p.state,
              timestamp: p.timestamp,
              color: EVENT_COLORS[p.type] || "#f472b6",
            },
            geometry: { type: "Point", coordinates: [p.lon, p.lat] },
          }))
        : [];

    map.getSource("hub-pillars")?.setData({
      type: "FeatureCollection",
      features: pillarFeatures,
    });
    map.getSource("hub-points")?.setData({
      type: "FeatureCollection",
      features: hubFeatures,
    });
    map.getSource("agg-arcs")?.setData({
      type: "FeatureCollection",
      features: arcFeatures,
    });
    map.getSource("ind-points")?.setData({
      type: "FeatureCollection",
      features: indFeatures,
    });
  }, [aggregated, filteredPoints, lod, selectedLoc, mapReady]);

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
    const map = mapRef.current;
    if (!map || !mapReady) return;

    const onArcMove = (e) => {
      map.getCanvas().style.cursor = "pointer";
      const f = e.features?.[0];
      if (!f) return;
      const p = f.properties;
      popupRef.current
        .setLngLat(e.lngLat)
        .setHTML(
          `<div style="font-size:12px;color:#0f172a">
            <b>${p.srcName} → ${p.dstName}</b><br/>
            ${p.count} connections · ${p.uniqueSuspects} suspect(s)<br/>
            <span style="color:#475569">${p.categories}</span>
          </div>`,
        )
        .addTo(map);
    };

    const onArcLeave = () => {
      map.getCanvas().style.cursor = "";
      popupRef.current?.remove();
    };

    const onArcClick = (e) => {
      const id = e.features?.[0]?.properties?.id;
      const found = aggregated.routeList.find((r) => r.id === id);
      if (found) {
        setSelectedArc(found);
        setSelectedLoc(null);
      }
    };

    const onHubClick = (e) => {
      const key = e.features?.[0]?.properties?.key;
      const found = aggregated.hubList.find((h) => h.key === key);
      if (found) {
        setSelectedLoc(found);
        setSelectedArc(null);
      }
    };

    const onClusterClick = (e) => {
      const f = e.features?.[0];
      if (!f) return;
      const clusterId = f.properties.cluster_id;
      map
        .getSource("ind-points")
        ?.getClusterExpansionZoom(clusterId, (err, z) => {
          if (err) return;
          pushCamHistory();
          map.easeTo({ center: f.geometry.coordinates, zoom: z });
        });
    };

    map.on("mousemove", "agg-arcs-layer", onArcMove);
    map.on("mouseleave", "agg-arcs-layer", onArcLeave);
    map.on("click", "agg-arcs-layer", onArcClick);
    map.on("click", "hub-points-layer", onHubClick);
    map.on("click", "clusters-layer", onClusterClick);

    return () => {
      map.off("mousemove", "agg-arcs-layer", onArcMove);
      map.off("mouseleave", "agg-arcs-layer", onArcLeave);
      map.off("click", "agg-arcs-layer", onArcClick);
      map.off("click", "hub-points-layer", onHubClick);
      map.off("click", "clusters-layer", onClusterClick);
    };
  }, [aggregated, mapReady, pushCamHistory]);

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
