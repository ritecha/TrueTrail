import { useState, useEffect } from "react";
import { nameOf, roleOf } from "../investigators.js";
import { updateCase, unreadCount } from "../store.js";
import Ledger, { API } from "./Ledger.jsx";
import GraphView from "./GraphView.jsx";
import { TimelineView, MapView } from "./TimeMap.jsx";
import UploadCard from "./UploadCard.jsx";
import TiltCard from "./TiltCard.jsx";
import GroupChat from "./GroupChat.jsx";
import AgentChat from "./AgentChat.jsx";

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

export default function WorkspaceView({ c, user, onBack }) {
  const hasEvidence = c.evidence && c.evidence.length > 0;
  const [tab, setTab] = useState("overview");
  const [refreshKey, setRefreshKey] = useState(0);
  const [agentOpen, setAgentOpen] = useState(false);

  const [loading, setLoading] = useState(false);
  const [graphError, setGraphError] = useState(null);
  const [timelineData, setTimelineData] = useState(null);
  const [transactionsData, setTransactionsData] = useState([]);
  const [callsData, setCallsData] = useState([]);
  const [engineData, setEngineData] = useState({ nodes: [], edges: [] });

  useEffect(() => {
    const controller = new AbortController();
    const { signal } = controller;
    setLoading(true);
    setGraphError(null);

    const fetchJson = async (url) => {
      const r = await fetch(url, { signal });
      if (!r.ok) {
        throw new Error(`${r.status} ${r.statusText} (${url})`);
      }
      return r.json();
    };

    const fetchData = async () => {
      try {
        const [tRes, gRes, callsRes, engRes] = await Promise.allSettled([
          fetchJson(`${API}/api/timeline`),
          fetchJson(`${API}/jaya/api/v1/records/transactions?limit=1000`),
          fetchJson(`${API}/jaya/api/v1/records/calls?limit=1000`),
          fetchJson(`${API}/jaya/api/v1/correlate/graph`),
        ]);

        if (signal.aborted) return;

        if (tRes.status === "fulfilled" && tRes.value?.status === "success") {
          setTimelineData(tRes.value.data);
        }

        if (gRes.status === "fulfilled") {
          const gData = gRes.value;
          setTransactionsData(Array.isArray(gData) ? gData : gData.items || []);
        } else if (gRes.reason?.name !== "AbortError") {
          setGraphError(
            gRes.reason?.message || "Could not load transactions for graph.",
          );
        }

        if (callsRes.status === "fulfilled") {
          const cData = callsRes.value;
          setCallsData(Array.isArray(cData) ? cData : cData.items || []);
        }

        if (engRes.status === "fulfilled" && engRes.value?.nodes) {
          setEngineData(engRes.value);
        }
      } catch (err) {
        if (err.name !== "AbortError" && !signal.aborted) {
          setGraphError(err.message || "Data fetch error");
        }
      } finally {
        if (!signal.aborted) setLoading(false);
      }
    };

    fetchData();
    return () => controller.abort();
  }, [refreshKey, c.caseId]);

  const unread = unreadCount(c, user.id);

  const onUploaded = (d) => {
    updateCase(c.id, (x) => {
      x.evidence.push({
        id: nid(),
        uid: user.id,
        file: d.file || d.filename || "Uploaded file",
        sha: d.sha256 ? d.sha256.slice(0, 16) : "mock",
        ts: new Date().toISOString(),
      });
      return x;
    });
    setRefreshKey((k) => k + 1);
  };

  const members = Array.isArray(c.members) ? c.members : [];
  const theories = Array.isArray(c.theories) ? c.theories : [];

  return (
    <div>
      <div
        className="ws-head"
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          flexWrap: "wrap",
          gap: "12px",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
          <button className="mini" onClick={onBack}>
            ← All cases
          </button>
          <div className="ws-title">
            <span className="case-id mono">{c.caseId}</span>
            <h2>{c.name}</h2>
          </div>
        </div>

        <button
          onClick={() => setAgentOpen(true)}
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: "8px",
            padding: "9px 18px",
            borderRadius: "999px",
            border: "1px solid #22d3ee",
            background:
              "linear-gradient(135deg, rgba(34,211,238,0.22), rgba(244,114,182,0.22))",
            color: "#ffffff",
            fontWeight: 600,
            fontSize: "13px",
            cursor: "pointer",
            boxShadow: "0 0 18px rgba(34,211,238,0.35)",
          }}
        >
          <span>✦</span>
          <span>Ask Case AI</span>
        </button>
      </div>

      <nav className="subtabs">
        {TABS.map(([k, l]) => (
          <button
            key={k}
            className={"tab-btn" + (tab === k ? " active" : "")}
            onClick={() => setTab(k)}
          >
            {l}
            {k === "chat" && unread > 0 ? ` (${unread})` : ""}
          </button>
        ))}
      </nav>

      {tab === "overview" && (
        <div style={{ display: "grid", gap: "16px" }}>
          <div className="panel neon-card">
            <h2 className="panel-title">Case overview</h2>
            <p className="muted" style={{ marginBottom: "16px" }}>
              {c.desc || "Active forensic investigation workspace."}
            </p>

            <div className="stat-row" style={{ marginBottom: "20px" }}>
              <div>
                <b>{transactionsData.length}</b>
                <span>transactions</span>
              </div>
              <div>
                <b>{timelineData?.events?.length ?? 0}</b>
                <span>timeline events</span>
              </div>
              <div>
                <b>{engineData?.nodes?.length ?? 0}</b>
                <span>graph entities</span>
              </div>
              <div>
                <b>{c.evidence?.length ?? 0}</b>
                <span>uploaded files</span>
              </div>
            </div>

            <div style={{ display: "flex", gap: "10px", flexWrap: "wrap" }}>
              <button className="neon-btn" onClick={() => setTab("graph")}>
                View Mule Network
              </button>
              <button className="mini" onClick={() => setTab("timeline")}>
                Open Timeline
              </button>
              <button className="mini" onClick={() => setTab("map")}>
                Open Map
              </button>
              <button className="mini" onClick={() => setTab("evidence")}>
                {hasEvidence ? "View Evidence" : "Upload Evidence"}
              </button>
            </div>
          </div>

          <div className="panel neon-card">
            <h3 className="panel-title">
              Investigators on this case ({members.length})
            </h3>
            {members.length === 0 ? (
              <p className="muted small">No investigators assigned.</p>
            ) : (
              <div style={{ display: "flex", gap: "10px", flexWrap: "wrap" }}>
                {members.map((m) => (
                  <div
                    key={m}
                    style={{
                      padding: "8px 12px",
                      borderRadius: "8px",
                      border: "1px solid var(--border-subtle)",
                      background: "var(--bg-base)",
                      fontSize: "13px",
                    }}
                  >
                    <b>{nameOf(m)}</b>
                    {roleOf(m) && (
                      <span className="muted small"> · {roleOf(m)}</span>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="panel neon-card">
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                marginBottom: "8px",
              }}
            >
              <h3 className="panel-title" style={{ margin: 0 }}>
                Case theories ({theories.length})
              </h3>
              <button className="mini" onClick={() => setTab("theories")}>
                + Add theory
              </button>
            </div>
            {theories.length === 0 ? (
              <p className="muted small">No theories added yet.</p>
            ) : (
              <div style={{ display: "grid", gap: "10px" }}>
                {theories.map((t) => (
                  <div
                    key={t.id}
                    style={{
                      padding: "10px 12px",
                      borderRadius: "8px",
                      border: "1px solid var(--border-subtle)",
                      background: "var(--bg-base)",
                    }}
                  >
                    <div style={{ fontWeight: 600 }}>{t.title}</div>
                    <div className="muted small" style={{ marginTop: "4px" }}>
                      {t.text}
                    </div>
                    <div
                      className="muted small"
                      style={{ marginTop: "4px", opacity: 0.7 }}
                    >
                      By {t.name || nameOf(t.uid)}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {tab === "graph" && (
        <GraphView
          transactions={transactionsData}
          calls={callsData}
          scores={{}}
          engine={engineData}
          loading={loading}
          error={graphError}
          onRetry={() => setRefreshKey((k) => k + 1)}
        />
      )}

      {tab === "timeline" &&
        (timelineData ? (
          <TimelineView data={timelineData} />
        ) : (
          <p className="muted p-4">Loading Timeline...</p>
        ))}

      {tab === "map" &&
        (timelineData ? (
          <MapView data={timelineData} />
        ) : (
          <p className="muted p-4">Loading Map...</p>
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
            <UploadCard actor={user.id} onDone={onUploaded} caseId={c.caseId} />
          </TiltCard>
          <div className="ev-list panel">
            <h3 className="ws-h">Uploaded to this case</h3>
            {c.evidence.map((e) => (
              <div key={e.id} className="ws-row">
                <span>{e.file}</span>
              </div>
            ))}
          </div>
          <div className="ev-ledger" style={{ gridColumn: "1 / -1" }}>
            <Ledger refreshKey={refreshKey} />
          </div>
        </div>
      )}

      {tab === "theories" && <Theories c={c} user={user} />}
      {tab === "chat" && <GroupChat c={c} user={user} />}

      {agentOpen && (
        <div className="drawer-back" onClick={() => setAgentOpen(false)}>
          <aside className="drawer" onClick={(e) => e.stopPropagation()}>
            <button
              className="drawer-x"
              onClick={() => setAgentOpen(false)}
              aria-label="Close"
            >
              ✕
            </button>
            <AgentChat key={c.id} user={user} c={c} />
          </aside>
        </div>
      )}
    </div>
  );
}

function Theories({ c, user }) {
  const [title, setTitle] = useState("");
  const [text, setText] = useState("");
  const theories = Array.isArray(c.theories) ? c.theories : [];

  const submit = (e) => {
    e.preventDefault();
    if (!title.trim() || !text.trim()) return;
    updateCase(c.id, (x) => {
      if (!Array.isArray(x.theories)) x.theories = [];
      x.theories.unshift({
        id: Date.now() + Math.random(),
        uid: user.id,
        name: user.name,
        title: title.trim(),
        text: text.trim(),
        ts: new Date().toISOString(),
      });
      return x;
    });
    setTitle("");
    setText("");
  };

  return (
    <div className="panel neon-card">
      <h2 className="panel-title">Case theories</h2>

      <form
        onSubmit={submit}
        style={{ display: "grid", gap: "10px", marginBottom: "20px" }}
      >
        <input
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="Theory title (e.g., Shared device across mule accounts)"
          style={{
            padding: "10px 12px",
            borderRadius: "8px",
            border: "1px solid var(--border-strong)",
            background: "var(--bg-base)",
            color: "inherit",
          }}
        />
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="Describe your hypothesis and supporting observations..."
          rows={3}
          style={{
            padding: "10px 12px",
            borderRadius: "8px",
            border: "1px solid var(--border-strong)",
            background: "var(--bg-base)",
            color: "inherit",
            resize: "vertical",
          }}
        />
        <div>
          <button type="submit" className="neon-btn">
            Add Theory
          </button>
        </div>
      </form>

      {theories.length === 0 ? (
        <p className="muted">No theories added yet.</p>
      ) : (
        <div style={{ display: "grid", gap: "10px" }}>
          {theories.map((t) => (
            <div
              key={t.id}
              style={{
                padding: "12px",
                borderRadius: "8px",
                border: "1px solid var(--border-subtle)",
                background: "var(--bg-base)",
              }}
            >
              <div style={{ fontWeight: 600 }}>{t.title}</div>
              <p className="muted small" style={{ margin: "6px 0" }}>
                {t.text}
              </p>
              <div className="muted small" style={{ opacity: 0.7 }}>
                Added by {t.name || nameOf(t.uid)}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
