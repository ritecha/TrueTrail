// Builds the money-flow graph from canonical transactions and structures nodes into clean, non-overlapping clusters.
const MIN_FLOW = 100000;
const MIN_PASSTHROUGH = 0.8;

export const ROLE = {
  victim: { label: "Source of funds", color: "#fbbf24" },
  mule: { label: "Mule (pass-through)", color: "#f472b6" },
  cashout: { label: "Terminal account", color: "#38bdf8" },
  handler: { label: "Likely handler", color: "#fb923c" },
  other: { label: "Other account", color: "#64748b" },
};

export const KIND_COLOR = {
  account: "#38bdf8",
  phone: "#2dd4bf",
  device: "#a78bfa",
  ip_address: "#fbbf24",
  vpa: "#22d3ee",
  ENTITY: "#38bdf8",
  EVENT: "#f472b6",
};

export function buildGraph(txns = [], calls = [], scores = {}) {
  const ok = (Array.isArray(txns) ? txns : []).filter(
    (t) => !t.status || String(t.status).toUpperCase() === "SUCCESS",
  );

  // 1) Identity: map UPI handles to account numbers so one person = one node
  const vpaToAcct = new Map();
  const names = new Map();
  for (const t of ok) {
    for (const s of ["sender", "receiver"]) {
      const a = t[s + "_account"],
        v = t[s + "_vpa"],
        n = t[s + "_name"];
      if (a && v) vpaToAcct.set(v, a);
      if (a && n && !names.has(a)) names.set(a, n);
    }
  }
  const idOf = (t, s) =>
    t[s + "_account"] ||
    (t[s + "_vpa"] && vpaToAcct.get(t[s + "_vpa"])) ||
    t[s + "_vpa"] ||
    null;

  // 2) Aggregate nodes and edges
  const nodes = new Map();
  const getNode = (id, fallback) => {
    if (!nodes.has(id))
      nodes.set(id, {
        id,
        name: names.get(id) || fallback || id,
        inSum: 0,
        outSum: 0,
        inCnt: 0,
        outCnt: 0,
        cashIn: 0,
        cashOut: 0,
        firstOut: Infinity,
        devices: new Map(),
        ips: new Map(),
        role: "other",
        phones: new Map(),
        inTimes: [],
        risk: scores[id]?.risk ?? null,
        reasons: scores[id]?.reasons ?? [],
      });
    return nodes.get(id);
  };

  const edges = new Map();
  for (const t of ok) {
    const s = idOf(t, "sender"),
      r = idOf(t, "receiver");
    const ts = Date.parse(t.timestamp);
    const amt = Number(t.amount || 0);
    if (s && r) {
      const a = getNode(s, t.sender_name),
        b = getNode(r, t.receiver_name);
      a.outSum += amt;
      a.outCnt++;
      b.inSum += amt;
      b.inCnt++;
      if (!Number.isNaN(ts)) {
        a.firstOut = Math.min(a.firstOut, ts);
        b.inTimes.push(ts);
      }
      if (t.sender_mobile)
        a.phones.set(t.sender_mobile, (a.phones.get(t.sender_mobile) || 0) + 1);
      if (t.device_id)
        a.devices.set(t.device_id, (a.devices.get(t.device_id) || 0) + 1);
      if (t.ip_address)
        a.ips.set(t.ip_address, (a.ips.get(t.ip_address) || 0) + 1);
      const k = s + ">" + r;
      const e = edges.get(k) || {
        source: s,
        target: r,
        total: 0,
        count: 0,
        first: Infinity,
        last: -Infinity,
        kind: "flow",
      };
      e.total += amt;
      e.count++;
      if (!Number.isNaN(ts)) {
        e.first = Math.min(e.first, ts);
        e.last = Math.max(e.last, ts);
      }
      edges.set(k, e);
    } else if (r) getNode(r, t.receiver_name).cashIn += amt;
    else if (s) getNode(s, t.sender_name).cashOut += amt;
  }

  // 3) Roles
  for (const n of nodes.values()) {
    const hi = Math.max(n.inSum, n.outSum),
      lo = Math.min(n.inSum, n.outSum);
    n.volume = hi;
    n.passthrough = hi ? lo / hi : 0;
    if (lo >= MIN_FLOW && n.passthrough >= MIN_PASSTHROUGH) n.role = "mule";
    else if (n.outSum >= MIN_FLOW && n.outSum >= 3 * n.inSum) n.role = "victim";
    else if (n.inSum >= MIN_FLOW && n.inSum >= 3 * n.outSum) n.role = "cashout";
  }

  const suspicious = [...nodes.values()].filter((n) => n.role !== "other");
  const sus = new Set(suspicious.map((n) => n.id));

  // 4) Shared device / IP between flagged accounts
  const byDevice = new Map();
  for (const n of suspicious)
    for (const d of n.devices.keys()) {
      if (!byDevice.has(d)) byDevice.set(d, []);
      byDevice.get(d).push(n);
    }
  const shared = [];
  for (const [device, list] of byDevice) {
    for (let i = 0; i < list.length; i++)
      for (let j = i + 1; j < list.length; j++) {
        const ips = [...list[i].ips.keys()].filter((ip) => list[j].ips.has(ip));
        shared.push({
          source: list[i].id,
          target: list[j].id,
          kind: "shared",
          device,
          ips,
        });
      }
  }

  // 4b) Handler from CDR
  const WINDOW = 10 * 60 * 1000;
  const flaggedPhones = new Set();
  const phoneOf = (n) =>
    [...n.phones.entries()].sort((a, b) => b[1] - a[1])[0]?.[0] ?? null;
  const mules = suspicious.filter((n) => n.role === "mule" && phoneOf(n));
  mules.forEach((m) => flaggedPhones.add(phoneOf(m)));
  const hits = new Map();
  for (const c of calls) {
    if (flaggedPhones.has(c.caller)) continue;
    const m = mules.find((x) => phoneOf(x) === c.callee);
    if (!m) continue;
    const ts = Date.parse(c.start_time);
    if (!m.inTimes.some((t) => ts >= t && ts - t <= WINDOW)) continue;
    if (!hits.has(c.caller)) hits.set(c.caller, new Map());
    const mm = hits.get(c.caller);
    mm.set(m.id, (mm.get(m.id) || 0) + 1);
  }
  let handler = null;
  for (const [phone, mm] of hits) {
    if (
      mm.size >= Math.max(3, Math.ceil(0.6 * mules.length)) &&
      (!handler || mm.size > handler.mules.length)
    )
      handler = {
        phone,
        mules: [...mm.entries()].map(([id, count]) => ({ id, count })),
      };
  }

  // 5) Summary
  const flowEdges = [...edges.values()].filter(
    (e) => sus.has(e.source) && sus.has(e.target),
  );
  const stats = {
    accounts: nodes.size,
    flagged: suspicious.length,
    entered: flowEdges
      .filter((e) => nodes.get(e.source)?.role === "victim")
      .reduce((s, e) => s + e.total, 0),
    routed: suspicious
      .filter((n) => n.role === "cashout")
      .reduce((s, n) => s + n.inSum, 0),
    from: flowEdges.length ? Math.min(...flowEdges.map((e) => e.first)) : null,
    to: flowEdges.length ? Math.max(...flowEdges.map((e) => e.last)) : null,
  };
  return {
    nodes: [...nodes.values()],
    edges: [...edges.values()],
    shared,
    sus,
    stats,
    handler,
  };
}

// Deterministic cluster-aware 2D layout seeding (eliminates spider-web hairball)
function seedClusterPositions(nodes) {
  const groups = new Map();
  for (const n of nodes) {
    const key =
      n.role === "engine" ? n.type || n.kind || "ENTITY" : n.role || "other";
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(n);
  }

  const anchors = {
    victim: { cx: -240, cy: 0, r: 65 },
    mule: { cx: 0, cy: 0, r: 105 },
    cashout: { cx: 240, cy: 0, r: 65 },
    handler: { cx: 0, cy: -175, r: 40 },
    other: { cx: 0, cy: 230, r: 190 },
  };

  let sectorIdx = 0;
  const totalGroups = Math.max(1, groups.size);
  const clusters = [];

  for (const [key, list] of groups) {
    const anchor = anchors[key] || {
      cx: Math.cos((sectorIdx / totalGroups) * Math.PI * 2) * 210,
      cy: Math.sin((sectorIdx / totalGroups) * Math.PI * 2) * 165,
      r: Math.min(140, 45 + Math.sqrt(list.length) * 18),
    };
    sectorIdx++;

    list.sort((a, b) => (b.volume || b.ctrl || 0) - (a.volume || a.ctrl || 0));
    list.forEach((n, i) => {
      const angle = i * 2.39996;
      const dist = anchor.r * Math.sqrt((i + 0.5) / Math.max(1, list.length));
      n.x = anchor.cx + Math.cos(angle) * dist;
      n.y = anchor.cy + Math.sin(angle) * dist;
      n.clusterKey = key;
    });

    clusters.push({
      key,
      label: ROLE[key]?.label || String(key).replaceAll("_", " "),
      color: ROLE[key]?.color || KIND_COLOR[key] || "#38bdf8",
      cx: anchor.cx,
      cy: anchor.cy,
      radius: anchor.r + 28,
      count: list.length,
    });
  }

  return clusters;
}

export function viewGraph(g, mode) {
  const label = (e) =>
    "₹" +
    Math.round((e.total || 0) / 1000) +
    "k" +
    (e.count > 1 ? " ×" + e.count : "");

  if (mode === "all") {
    const nodes = g.nodes.map((n) => ({ ...n }));
    const clusters = seedClusterPositions(nodes);
    const links = [...g.edges, ...g.shared].map((e) => ({
      ...e,
      label: e.kind === "flow" ? label(e) : "",
    }));
    return { nodes, links, clusters };
  }

  const inChain = g.nodes.filter((n) => g.sus.has(n.id));
  const flow = g.edges.filter(
    (e) => g.sus.has(e.source) && g.sus.has(e.target),
  );
  const ordered = [];
  const seen = new Set();
  let cur = inChain.find((n) => n.role === "victim") || inChain[0];
  while (cur && !seen.has(cur.id)) {
    ordered.push(cur);
    seen.add(cur.id);
    const next = flow
      .filter((e) => e.source === cur.id && !seen.has(e.target))
      .sort((a, b) => b.total - a.total)[0];
    cur = next && inChain.find((n) => n.id === next.target);
  }
  for (const n of inChain) if (!seen.has(n.id)) ordered.push(n);

  const ns = ordered.map((n, i, arr) => ({
    ...n,
    fx: (i - (arr.length - 1) / 2) * 135,
    fy: i % 2 ? 42 : -42,
    clusterKey: n.role,
  }));

  const links = [
    ...g.edges.filter((e) => g.sus.has(e.source) && g.sus.has(e.target)),
    ...g.shared,
  ].map((e) => ({ ...e, label: e.kind === "flow" ? label(e) : "" }));

  if (g.handler) {
    const hid = "handler:" + g.handler.phone;
    ns.push({
      id: hid,
      name: "Likely handler",
      phone: g.handler.phone,
      role: "handler",
      volume: 0,
      passthrough: 0,
      inSum: 0,
      outSum: 0,
      inCnt: 0,
      outCnt: 0,
      cashIn: 0,
      cashOut: 0,
      called: g.handler.mules.length,
      fx: 0,
      fy: -135,
      clusterKey: "handler",
      reasons: [],
    });
    for (const m of g.handler.mules)
      links.push({
        source: hid,
        target: m.id,
        kind: "call",
        label: m.count + (m.count > 1 ? " calls" : " call"),
      });
  }

  return { nodes: ns, links, clusters: [] };
}

export function viewEngine(engine, fallbackGraph = null) {
  const rawNodes = Array.isArray(engine?.nodes) ? engine.nodes : [];
  const rawEdges = Array.isArray(engine?.edges)
    ? engine.edges
    : Array.isArray(engine?.links)
      ? engine.links
      : [];

  let nodes = [];
  let links = [];

  if (rawNodes.length === 0 && fallbackGraph?.nodes?.length > 0) {
    nodes = fallbackGraph.nodes.map((n) => ({
      ...n,
      label: n.name,
      kind: n.role === "other" ? "account" : "ENTITY",
      type: n.role,
      ctrl: n.role === "other" ? 0.2 : 0.8,
      risk: n.passthrough || 0,
      role: "engine",
    }));
    links = fallbackGraph.edges.map((e) => ({
      source: e.source,
      target: e.target,
      kind: "flow",
      total: e.total || 0,
      label: "",
    }));
  } else {
    const nodeIds = new Set(rawNodes.map((n) => n.id));
    nodes = rawNodes.map((n) => ({ ...n, role: "engine" }));
    links = rawEdges
      .filter((e) => {
        const s = typeof e.source === "object" ? e.source?.id : e.source;
        const t = typeof e.target === "object" ? e.target?.id : e.target;
        return nodeIds.has(s) && nodeIds.has(t);
      })
      .map((e) => ({
        source: typeof e.source === "object" ? e.source.id : e.source,
        target: typeof e.target === "object" ? e.target.id : e.target,
        kind: e.kind === "TRANSFERRED" ? "flow" : "link",
        total: e.amount || e.total || 0,
        label: e.role || "",
      }));
  }

  const clusters = seedClusterPositions(nodes);
  return { nodes, links, clusters };
}
