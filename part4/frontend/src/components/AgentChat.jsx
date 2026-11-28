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
const storageKey = (caseId) => `truetrail.agent_chat.${caseId}`;

const loadHistory = (caseId) => {
  try {
    const raw = localStorage.getItem(storageKey(caseId));
    const parsed = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
};

function Answer({ text, onRef }) {
  return String(text || "")
    .split(REF)
    .map((part, i) =>
      /^\[(txn|call|ip|acct|note|ev):/.test(part) ? (
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
  const [msgs, setMsgs] = useState(() => loadHistory(c.id));
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [open, setOpen] = useState(null);
  const [focused, setFocused] = useState(false);
  const end = useRef(null);

  useEffect(() => {
    setMsgs(loadHistory(c.id));
    setOpen(null);
  }, [c.id]);

  useEffect(() => {
    try {
      localStorage.setItem(storageKey(c.id), JSON.stringify(msgs));
    } catch {
      /* ignore */
    }
  }, [c.id, msgs]);

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
          investigator,
          investigator_id: user?.id,
          case_id: c.id,
          case_label: c.caseId,
          case_name: c.name,
          has_data: !!c.primary || (c.evidence && c.evidence.length > 0),
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
    } catch (err) {
      setMsgs((m) => [
        ...m,
        {
          role: "assistant",
          text: err.message || "Agent request failed.",
          error: true,
        },
      ]);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div
      className="agent"
      style={{
        display: "flex",
        flexDirection: "column",
        height: "100%",
        boxSizing: "border-box",
      }}
    >
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          gap: "10px",
          paddingRight: "46px",
          marginBottom: "10px",
        }}
      >
        <div style={{ minWidth: 0 }}>
          <h2 className="panel-title" style={{ margin: 0 }}>
            Case assistant
          </h2>
          <p
            className="muted small"
            style={{
              margin: 0,
              whiteSpace: "nowrap",
              overflow: "hidden",
              textOverflow: "ellipsis",
            }}
          >
            {c.caseId} · {c.name}
          </p>
        </div>
        {msgs.length > 0 && (
          <button
            className="mini"
            onClick={() => {
              setMsgs([]);
              localStorage.removeItem(storageKey(c.id));
            }}
          >
            Clear Chat
          </button>
        )}
      </div>

      {msgs.length === 0 && (
        <div className="chips" style={{ marginBottom: "12px" }}>
          {SUGGEST.map((s) => (
            <button key={s} className="chipbtn" onClick={() => send(s)}>
              {s}
            </button>
          ))}
        </div>
      )}

      <div
        className="agent-log"
        style={{
          flex: 1,
          overflowY: "auto",
          display: "flex",
          flexDirection: "column",
          gap: "10px",
          padding: "4px 2px",
        }}
      >
        {msgs.map((m, i) => {
          const isUser = m.role === "user";
          return (
            <div
              key={i}
              className={"amsg " + m.role + (m.error ? " err" : "")}
              style={{
                display: "flex",
                flexDirection: "column",
                alignItems: isUser ? "flex-end" : "flex-start",
                width: "100%",
              }}
            >
              <div
                className="abubble"
                style={{
                  maxWidth: "84%",
                  padding: "10px 13px",
                  borderRadius: isUser
                    ? "14px 14px 4px 14px"
                    : "14px 14px 14px 4px",
                  background: isUser
                    ? "rgba(34, 211, 238, 0.18)"
                    : "rgba(15, 23, 42, 0.85)",
                  border: isUser
                    ? "1px solid rgba(34, 211, 238, 0.45)"
                    : "1px solid var(--border-subtle)",
                  textAlign: "left",
                  lineHeight: 1.45,
                }}
              >
                {!isUser ? (
                  <Answer
                    text={m.text}
                    onRef={(ref) =>
                      setOpen(
                        open?.i === i && open?.ref === ref ? null : { i, ref },
                      )
                    }
                  />
                ) : (
                  m.text
                )}
              </div>
              {open?.i === i && (
                <pre
                  className="refbox"
                  style={{ maxWidth: "90%", overflowX: "auto" }}
                >
                  {JSON.stringify(
                    m.citations?.find((x) => x.ref === open.ref)?.record || {
                      ref: open.ref,
                    },
                    null,
                    2,
                  )}
                </pre>
              )}
            </div>
          );
        })}
        {busy && <div className="muted small">Checking case records…</div>}
        <div ref={end} />
      </div>

      {/* Pretty glassmorphic full-width input bar */}
      <form
        className="agent-in"
        onSubmit={(e) => {
          e.preventDefault();
          send();
        }}
        style={{
          display: "flex",
          alignItems: "center",
          gap: "8px",
          width: "100%",
          marginTop: "12px",
          padding: "6px 8px 6px 14px",
          borderRadius: "999px",
          background: "rgba(15, 23, 42, 0.9)",
          border: focused
            ? "1px solid #22d3ee"
            : "1px solid rgba(148, 163, 184, 0.28)",
          boxShadow: focused
            ? "0 0 16px rgba(34, 211, 238, 0.25)"
            : "0 4px 14px rgba(0, 0, 0, 0.25)",
          transition: "border-color 0.2s ease, box-shadow 0.2s ease",
          boxSizing: "border-box",
        }}
      >
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onFocus={() => setFocused(true)}
          onBlur={() => setFocused(false)}
          placeholder="Ask anything about this case..."
          disabled={busy}
          style={{
            flex: 1,
            width: "100%",
            minWidth: 0,
            border: "none",
            outline: "none",
            background: "transparent",
            color: "#f8fafc",
            fontSize: "13px",
          }}
        />
        <button
          className="neon-btn"
          type="submit"
          disabled={busy || !input.trim()}
          style={{
            borderRadius: "999px",
            padding: "7px 16px",
            fontSize: "12px",
            fontWeight: 600,
          }}
        >
          {busy ? "…" : "Send"}
        </button>
      </form>
    </div>
  );
}
