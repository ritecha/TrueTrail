import { useEffect, useState } from "react";

const KEY = "truetrail.cases.v1";
const EVT = "tt-cases";
const d = (daysAgo, h = 10) =>
  new Date(Date.now() - daysAgo * 864e5 - (10 - h) * 36e5).toISOString();

// Helper to auto-generate Case ID
const generateCaseId = () =>
  `CR-2026-${Math.floor(1000 + Math.random() * 9000)}`;

const seed = () => [
  {
    id: "c1",
    caseId: "CR-2026-001",
    name: "Mule network – Rajesh Kumar Sharma",
    status: "Active",
    primary: true,
    desc: "Layered UPI transfers through mule accounts on 14 March 2026. Data loaded: bank, UPI, calls, IP logs.",
    owner: "inv.sharma",
    members: ["inv.sharma", "inv.verma", "inv.khan", "inv.ritika"],
    seen: {},
    evidence: [],
    chat: [
      {
        id: 1,
        uid: "inv.verma",
        name: "SI Verma",
        text: "IP logs show two accounts on the same device. Checking timestamps.",
        ts: d(1, 11),
      },
      {
        id: 2,
        uid: "inv.khan",
        name: "ASI Khan",
        text: "Fund trace matches. Money leaves within minutes of each credit.",
        ts: d(1, 12),
      },
    ],
    theories: [
      {
        id: 1,
        uid: "inv.verma",
        name: "SI Verma",
        title: "Handler uses one phone for all mule accounts",
        text: "Shared device/IP across three mule accounts suggests one operator. No direct proof of identity yet.",
        ts: d(1, 11),
      },
    ],
    events: [
      {
        id: 1,
        uid: "inv.verma",
        type: "evidence",
        text: "uploaded device_dump.json",
        ts: d(2, 9),
      },
    ],
  },
];

// Evidence rows must have id/uid/sha/ts (the UI uses them as React keys and for "who/when").
// Cases saved by the create-workspace flow had raw upload results without them.
const fixEvidence = (c) => ({
  ...c,
  evidence: (c.evidence || []).map((ev, i) => ({
    ...ev,
    id: ev.id ?? `ev-${i}-${(ev.sha256 || ev.sha || ev.file || "").slice(0, 12)}`,
    uid: ev.uid ?? c.owner,
    sha: ev.sha ?? (ev.sha256 || "").slice(0, 16),
    ts: ev.ts ?? c.events?.[0]?.ts ?? new Date().toISOString(),
  })),
});

export function loadCases() {
  try {
    const c = JSON.parse(localStorage.getItem(KEY));
    if (Array.isArray(c) && c.length) return c.map(fixEvidence);
  } catch {
    /* fall through */
  }
  const s = seed();
  try {
    localStorage.setItem(KEY, JSON.stringify(s));
  } catch {
    /* ignore */
  }
  return s;
}
export function saveCases(c) {
  try {
    localStorage.setItem(KEY, JSON.stringify(c));
  } catch {
    /* ignore */
  }
  window.dispatchEvent(new Event(EVT));
}
export function updateCase(id, fn) {
  saveCases(loadCases().map((c) => (c.id === id ? fn(structuredClone(c)) : c)));
}
export function createCase({
  caseId,
  name,
  desc,
  owner,
  members,
  initialEvidence = [],
}) {
  const c = {
    id: "c" + Date.now(),
    caseId: caseId || generateCaseId(), // Auto-generate if empty
    name,
    desc,
    status: "Active",
    primary: false,
    owner,
    members: [...new Set([owner, ...members])],
    seen: {},
    evidence: initialEvidence.map((ev, i) => ({
      id: `ev-${Date.now()}-${i}`,
      uid: owner,
      file: ev.file,
      sha: (ev.sha256 || "").slice(0, 16),
      ts: new Date().toISOString(),
    })),
    chat: [],
    theories: [],
    events: initialEvidence.map((ev, i) => ({
      id: `evt-init-${Date.now()}-${i}`,
      uid: owner,
      type: "evidence",
      text: `uploaded ${ev.file}`,
      ts: new Date().toISOString(),
    })),
  };
  saveCases([...loadCases(), c]);
  return c;
}
export function unreadCount(c, uid) {
  const since = c.seen?.[uid] ?? "";
  return c.events.filter((e) => e.uid !== uid && e.ts > since).length;
}
export function useCases() {
  const [cases, setCases] = useState(loadCases);
  useEffect(() => {
    const sync = () => setCases(loadCases());
    window.addEventListener("storage", sync);
    window.addEventListener(EVT, sync);
    return () => {
      window.removeEventListener("storage", sync);
      window.removeEventListener(EVT, sync);
    };
  }, []);
  return cases;
}
export const ago = (iso) => {
  const m = Math.max(1, Math.round((Date.now() - new Date(iso)) / 6e4));
  return m < 60
    ? `${m}m ago`
    : m < 1440
      ? `${Math.round(m / 60)}h ago`
      : `${Math.round(m / 1440)}d ago`;
};
