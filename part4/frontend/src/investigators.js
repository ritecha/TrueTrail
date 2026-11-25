// Name directory. Sign-in is handled by Clerk now, so there are NO passwords here any more.
// DEMO_DIRECTORY only lets the old sample case (c1) show readable names for its original investigators.
export const DEMO_DIRECTORY = [
  { id: "inv.sharma", name: "Insp. Sharma", role: "Lead Investigator" },
  { id: "inv.verma", name: "SI Verma", role: "Cyber Forensics" },
  { id: "inv.khan", name: "ASI Khan", role: "Financial Analyst" },
  { id: "inv.ritika", name: "Ritika", role: "Investigator" },
];
export const INVESTIGATORS = DEMO_DIRECTORY; // kept so older imports keep working

// Real (Clerk) users are remembered here so avatars/chat show names instead of "user_2abc...".
const KEY = "truetrail.names";
const read = () => { try { return JSON.parse(localStorage.getItem(KEY)) || {}; } catch { return {}; } };
export function rememberUser(id, name, role = "Investigator") {
  const m = read();
  if (m[id]?.name === name) return;
  m[id] = { name, role };
  try { localStorage.setItem(KEY, JSON.stringify(m)); } catch { /* ignore */ }
}
export const nameOf = (id) => read()[id]?.name ?? DEMO_DIRECTORY.find((i) => i.id === id)?.name ?? "Investigator";
export const roleOf = (id) => read()[id]?.role ?? DEMO_DIRECTORY.find((i) => i.id === id)?.role ?? "";
// Teammates who have signed in on this browser (shown in "Add Investigators").
export const knownUsers = () => Object.entries(read()).map(([id, v]) => ({ id, ...v }));
