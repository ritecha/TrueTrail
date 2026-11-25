import { useEffect, useRef, useState } from "react";
import { API } from "./Ledger.jsx";
import { nameOf } from "../investigators.js";

const SUGGEST = [
  "Who is the likely handler, and what is the evidence?",
  "Trace the money from Rajesh Kumar Sharma's account.",
  "Which accounts look like mules, and why?",
  "Which accounts share a device or IP address?",
  "What happened between 05:40 and 06:00 UTC on 14 March 2026?",
  "What evidence has been uploaded to this case?",
];
const REF = /(\[(?:txn|call|ip|acct|note|ev):[^\]\s]+\])/g;

function Answer({ text, onRef }) {
  return text.split(REF).map((part, i) =>
    REF.test(part) || /^\[(txn|call|ip|acct|note|ev):/.test(part) ? (
      <button
        key={i}
        className="refchip"
        onClick={() => onRef(part.slice(1, -1))}
        title="Show the record"
      >
        {part.slice(1, 12)}…
      </button>
    ) : (
      <span key={i}>{part}</span>
    ),
  );
}

export default function AgentChat({ user, c }) {
  const investigator = user?.name || "Investigator";
  const [msgs, setMsgs] = useState([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [open, setOpen] = useState(null); // {i, ref}
  const end = useRef(null);
  useEffect(() => {
    end.current?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [msgs, busy]);

  const send = async (q) => {
    q = (q ?? input).trim();
    if (!q || busy) return;
    setInput("");
    setOpen(null);
    const history = msgs
      .filter((m) => !m.error)
      .map((m) => ({ role: m.role, content: m.text }));
    setMsgs((m) => [...m, { role: "user", text: q }]);
    setBusy(true);
    try {
      const r = await fetch(`${API}/agent/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question: q,
          history,
          investigator, // Clerk display name
          investigator_id: user?.id, // Clerk user id
          case_id: c.id,
          case_label: c.caseId,
          case_name: c.name,
          has_data: !!c.primary, // only the primary case has the loaded dataset
          members: (c.members || []).map((m) => nameOf(m)),
          notes: (c.theories || []).map((t) => ({
            id: t.id,
            author: t.name,
            text: `${t.title}: ${t.text}`,
          })),
          evidence: (c.evidence || []).map((ev) => ({
            id: ev.id,
            file: ev.file,
            sha: ev.sha,
            by: nameOf(ev.uid),
            ts: ev.ts,
          })),
        }),
      });
      const d = await r.json();
      if (!r.ok) throw new Error(d.detail || "The assistant could not answer.");
      setMsgs((m) => [
        ...m,
        {
          role: "assistant",
          text: d.answer,
          citations: d.citations,
          verified: d.verified,
          tools: d.tools_used,
        },
      ]);
    } catch (e) {
      setMsgs((m) => [
        ...m,
        {
          role: "assistant",
          error: true,
          text: e.message.includes("fetch")
            ? "Backend offline. Start the API on port 8001."
            : e.message,
        },
      ]);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="panel neon-card agent">
      <h2 className="panel-title">Case assistant · {c.caseId}</h2>
      <p className="muted small">
        Answers come only from this case's evidence and notes, with the source
        record cited for every fact. Patterns are not proof.
      </p>

      <div className="agent-msgs">
        {msgs.length === 0 && (
          <div className="agent-empty">
            <p className="muted">Try asking:</p>
            <div className="agent-suggest">
              {SUGGEST.map((s) => (
                <button
                  key={s}
                  className="chipbtn on"
                  style={{ "--c": "#22d3ee" }}
                  onClick={() => send(s)}
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}
        {msgs.map((m, i) => (
          <div key={i} className={"bubble " + m.role + (m.error ? " err" : "")}>
            <div className="bubble-text">
              {m.role === "assistant" && !m.error ? (
                <Answer text={m.text} onRef={(ref) => setOpen({ i, ref })} />
              ) : (
                m.text
              )}
            </div>
            {m.role === "assistant" && !m.error && (
              <div className={"verify " + (m.verified ? "ok" : "warn")}>
                {m.verified
                  ? `✓ Every cited record exists in the case data${m.tools?.length ? " · looked up: " + [...new Set(m.tools)].join(", ") : ""}`
                  : "Could not be fully verified. Treat with caution."}
              </div>
            )}
            {open?.i === i && (
              <pre className="record">
                {JSON.stringify(
                  m.citations?.find((c) => c.ref === open.ref)?.record ??
                    "record not found",
                  null,
                  2,
                )}
              </pre>
            )}
          </div>
        ))}
        {busy && (
          <div className="bubble assistant">
            <span className="dots">
              <i />
              <i />
              <i />
            </span>
          </div>
        )}
        <div ref={end} />
      </div>

      <div className="agent-input">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && send()}
          placeholder="Ask about this case…"
          disabled={busy}
        />
        <button
          className="neon-btn"
          onClick={() => send()}
          disabled={busy || !input.trim()}
        >
          Ask
        </button>
      </div>
    </div>
  );
}
