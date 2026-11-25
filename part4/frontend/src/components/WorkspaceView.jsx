import { useMemo, useState } from "react";
import { nameOf, roleOf } from "../investigators.js";
import { updateCase, unreadCount, ago } from "../store.js";
import Ledger from "./Ledger.jsx";
import GraphView from "./GraphView.jsx";
import { TimelineView, MapView } from "./TimeMap.jsx";
import UploadCard from "./UploadCard.jsx";
import TiltCard from "./TiltCard.jsx";
import GroupChat from "./GroupChat.jsx";

// ❌ Purane static JSON imports hata diye gaye hain

const TABS = [
  ["overview", "Overview"],
  ["graph", "Graph"],
  ["timeline", "Timeline"],
  ["map", "Map"],
  ["evidence", "Evidence"],
  ["theories", "Theories"],
  ["chat", "Team chat"],
];
const nid = () => Date.now() + Math.random();

function Empty({ what }) {
  return (
    <div
      className="panel empty-state"
      style={{ textAlign: "center", padding: "40px" }}
    >
      <h3>No data for this case yet</h3>
      <p className="muted">
        The {what} is built from the evidence investigators upload. Add files in
        the Evidence tab.
      </p>
    </div>
  );
}

export default function WorkspaceView({ c, user, onBack }) {
  const hasEvidence = c.evidence && c.evidence.length > 0;
  const [tab, setTab] = useState(hasEvidence ? "overview" : "evidence"); // Default to Evidence if empty
  const [refreshKey, setRefreshKey] = useState(0);

  // ✅ Empty States (Kyunki JSON files delete ho chuki hain)
  const txns = useMemo(() => [], []);
  const calls = useMemo(() => [], []);
  const scores = useMemo(() => ({}), []);
  const engine = useMemo(() => ({}), []);
  const timeline = useMemo(() => null, []);

  const unread = unreadCount(c, user.id);

  const onUploaded = (d) => {
    updateCase(c.id, (x) => {
      x.evidence.push({
        id: nid(),
        uid: user.id,
        file: d.file,
        sha: d.sha256 ? d.sha256.slice(0, 16) : "mock-sha-12345",
        ts: new Date().toISOString(),
      });
      x.events.push({
        id: nid(),
        uid: user.id,
        type: "evidence",
        text: `uploaded ${d.file}`,
        ts: new Date().toISOString(),
      });
      return x;
    });
    setRefreshKey((k) => k + 1);
  };
  const markRead = () =>
    updateCase(c.id, (x) => {
      x.seen[user.id] = new Date().toISOString();
      return x;
    });

  return (
    <div>
      <div className="ws-head">
        <button className="mini" onClick={onBack}>
          ← All cases
        </button>
        <div className="ws-title">
          <span className="case-id mono">{c.caseId}</span>
          <h2>{c.name}</h2>
        </div>
        <div className="avatars">
          {c.members.map((m) => (
            <span
              key={m}
              className="avatar sm"
              title={`${nameOf(m)} · ${roleOf(m)}`}
            >
              {nameOf(m)[0]}
            </span>
          ))}
        </div>
      </div>
      <nav className="subtabs">
        {TABS.map(([k, l]) => (
          <button
            key={k}
            className={"tab-btn" + (tab === k ? " active" : "")}
            onClick={() => setTab(k)}
            disabled={k === "overview" && !hasEvidence} // OVERVIEW LOCKED
            style={{
              opacity: k === "overview" && !hasEvidence ? 0.4 : 1,
              cursor:
                k === "overview" && !hasEvidence ? "not-allowed" : "pointer",
            }}
          >
            {l}
            {k === "overview" && unread > 0 && <i className="dot" />}
          </button>
        ))}
      </nav>

      {tab === "overview" && (
        <Overview
          c={c}
          user={user}
          unread={unread}
          markRead={markRead}
          setTab={setTab}
        />
      )}

      {tab === "graph" &&
        (hasEvidence ? (
          <div className="gt-split">
            <aside className="gt-left">
              <div className="gt-title">Timeline</div>
              {/* ✅ Safe check lagaya hai taaki empty data pe crash na ho */}
              {timeline ? (
                <TimelineView data={timeline} />
              ) : (
                <p className="muted p-4">No timeline data.</p>
              )}
            </aside>
            <GraphView
              transactions={txns}
              calls={calls}
              scores={scores}
              engine={engine}
            />
          </div>
        ) : (
          <Empty what="graph" />
        ))}

      {tab === "timeline" &&
        (hasEvidence ? (
          timeline ? (
            <TimelineView data={timeline} />
          ) : (
            <Empty what="timeline" />
          )
        ) : (
          <Empty what="timeline" />
        ))}

      {tab === "map" &&
        (hasEvidence ? (
          timeline ? (
            <MapView data={timeline} />
          ) : (
            <Empty what="map" />
          )
        ) : (
          <Empty what="map" />
        ))}

      {tab === "evidence" && (
        <div
          className="ev-layout"
          style={{
            display: "grid",
            gridTemplateColumns: "minmax(300px, 1fr) 2fr",
            gap: "20px",
          }}
        >
          <TiltCard className="ingest-card ev-tilt">
            <h2>ADD EVIDENCE</h2>
            <p className="sub">{c.caseId}</p>
            <UploadCard actor={user.id} onDone={onUploaded} />
          </TiltCard>
          <div className="ev-list panel">
            <h3 className="ws-h">Uploaded to this case</h3>
            {c.evidence.length === 0 ? (
              <p className="muted small">Nothing uploaded yet.</p>
            ) : (
              [...c.evidence].reverse().map((e) => (
                <div
                  key={e.id}
                  className="ws-row"
                  style={{
                    borderBottom: "1px solid var(--border-subtle)",
                    padding: "12px 0",
                  }}
                >
                  <span>
                    {e.file}
                    <br />
                    <span className="muted small">
                      {nameOf(e.uid)} · {ago(e.ts)}
                    </span>
                  </span>
                  <span className="mono">{e.sha}…</span>
                </div>
              ))
            )}
          </div>
          {hasEvidence && (
            <div className="ev-ledger" style={{ gridColumn: "1 / -1" }}>
              <Ledger refreshKey={refreshKey} />
            </div>
          )}
        </div>
      )}
      {tab === "theories" && <Theories c={c} user={user} />}
      {tab === "chat" && <GroupChat c={c} user={user} />}
    </div>
  );
}

// Overview and Theories functions remain exactly as you had them...
function Overview({ c, user, unread, markRead, setTab }) {
  const since = c.seen?.[user.id] ?? "";
  const events = [...c.events].reverse().slice(0, 8);
  const theories = [...c.theories].reverse().slice(0, 3);
  return (
    <div className="ov-grid">
      <div className="panel">
        <h3 className="ws-h">Investigators ({c.members.length})</h3>
        {c.members.map((m) => (
          <div key={m} className="ws-row">
            <span className="who">
              <span className="avatar sm">{nameOf(m)[0]}</span>
              {nameOf(m)}
            </span>
            <span className="muted small">
              {m === c.owner ? "Owner · " : ""}
              {roleOf(m)}
            </span>
          </div>
        ))}
        <p className="muted small" style={{ marginTop: 12 }}>
          {c.desc}
        </p>
      </div>
      <div className="panel">
        <div className="ws-top">
          <h3 className="ws-h">
            Notifications{" "}
            {unread > 0 && <span className="badge">{unread} new</span>}
          </h3>
          {unread > 0 && (
            <button className="mini" onClick={markRead}>
              Mark all read
            </button>
          )}
        </div>
        {events.length === 0 ? (
          <p className="muted small">No activity yet.</p>
        ) : (
          events.map((e) => (
            <div key={e.id} className="ws-row">
              <span>
                {e.uid !== user.id && e.ts > since && <i className="dot" />}
                <b>{e.uid === user.id ? "You" : nameOf(e.uid)}</b> {e.text}
              </span>
              <span className="muted small">{ago(e.ts)}</span>
            </div>
          ))
        )}
      </div>
      <div className="panel ov-wide">
        <div className="ws-top">
          <h3 className="ws-h">
            Team theories <span className="tag warn">not proven</span>
          </h3>
          <button className="mini" onClick={() => setTab("theories")}>
            View all
          </button>
        </div>
        {theories.length === 0 ? (
          <p className="muted small">No theories yet.</p>
        ) : (
          theories.map((t) => (
            <div key={t.id} className="theory">
              <b>{t.title}</b>
              <p className="muted small">{t.text}</p>
              <span className="muted small">
                {nameOf(t.uid)} · {ago(t.ts)}
              </span>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

function Theories({ c, user }) {
  const [t, setT] = useState({ title: "", text: "" });
  const add = () => {
    if (!t.title.trim()) return;
    updateCase(c.id, (x) => {
      x.theories.push({
        id: nid(),
        uid: user.id,
        name: user.name,
        title: t.title.trim(),
        text: t.text.trim(),
        ts: new Date().toISOString(),
      });
      x.events.push({
        id: nid(),
        uid: user.id,
        type: "theory",
        text: `added a theory: ${t.title.trim()}`,
        ts: new Date().toISOString(),
      });
      return x;
    });
    setT({ title: "", text: "" });
  };
  return (
    <div className="panel">
      <h2 className="panel-title">Theories</h2>
      <div className="ws-form" style={{ maxWidth: 640, marginTop: "16px" }}>
        <input
          value={t.title}
          onChange={(e) => setT({ ...t, title: e.target.value })}
          placeholder="Theory title"
        />
        <textarea
          rows="2"
          value={t.text}
          onChange={(e) => setT({ ...t, text: e.target.value })}
          placeholder="What do you think happened?"
        />
        <button className="neon-btn" onClick={add} disabled={!t.title.trim()}>
          Add theory
        </button>
      </div>
      <div style={{ marginTop: 18 }}>
        {c.theories.length === 0 ? (
          <p className="muted small">No theories yet.</p>
        ) : (
          [...c.theories].reverse().map((x) => (
            <div key={x.id} className="theory">
              <b>{x.title}</b>
              <p className="muted small">{x.text}</p>
              <span className="muted small">
                {nameOf(x.uid)} · {ago(x.ts)}
              </span>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
