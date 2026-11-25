import { useEffect, useRef, useState } from "react";
import { nameOf } from "../investigators.js";
import { updateCase } from "../store.js";

// Team chat for one case (stored with the case; see store.js for limits).
export default function GroupChat({ c, user }) {
  const [text, setText] = useState("");
  const end = useRef(null);
  useEffect(() => { end.current?.scrollIntoView({ block: "nearest", behavior: "smooth" }); }, [c.chat.length]);

  const send = () => {
    const t = text.trim();
    if (!t) return;
    updateCase(c.id, (x) => {
      x.chat = [...x.chat, { id: Date.now(), uid: user.id, name: user.name, text: t, ts: new Date().toISOString() }].slice(-200);
      return x;
    });
    setText("");
  };
  const names = c.members.map((m) => nameOf(m)).join(", ");

  return (
    <section className="panel neon-card gchat">
      <h2 className="panel-title">Team chat · {c.caseId}</h2>
      <p className="muted small">{c.members.length} investigators · {names}</p>
      <div className="agent-msgs">
        {c.chat.length === 0 && <p className="muted">No messages yet. Start the discussion.</p>}
        {c.chat.map((m) => (
          <div key={m.id} className={"bubble " + (m.uid === user.id ? "user" : "assistant")}>
            <div className="gc-meta">{m.uid === user.id ? "You" : m.name} · {m.ts.slice(11, 16)}</div>
            <div className="bubble-text">{m.text}</div>
          </div>
        ))}
        <div ref={end} />
      </div>
      <div className="agent-input">
        <input value={text} onChange={(e) => setText(e.target.value)} onKeyDown={(e) => e.key === "Enter" && send()} placeholder="Message the team…" />
        <button className="neon-btn" onClick={send} disabled={!text.trim()}>Send</button>
      </div>
    </section>
  );
}
