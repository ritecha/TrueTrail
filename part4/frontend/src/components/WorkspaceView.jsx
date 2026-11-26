import { useState, useEffect } from "react";
import { updateCase, unreadCount } from "../store.js";
import Ledger from "./Ledger.jsx";
import GraphView from "./GraphView.jsx";
import { TimelineView, MapView } from "./TimeMap.jsx";
import UploadCard from "./UploadCard.jsx";
import TiltCard from "./TiltCard.jsx";
import GroupChat from "./GroupChat.jsx";

const API_BASE = "https://digitalevidencebytruetrail-backend.onrender.com";

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
  const [tab, setTab] = useState(hasEvidence ? "overview" : "evidence");
  const [refreshKey, setRefreshKey] = useState(0);

  const [loading, setLoading] = useState(false);
  const [timelineData, setTimelineData] = useState(null);
  const [transactionsData, setTransactionsData] = useState([]);
  const [engineData, setEngineData] = useState({ nodes: [], edges: [] });

  useEffect(() => {
    let isMounted = true;
    setLoading(true);

    const fetchData = async () => {
      try {
        const [tRes, jayaTlRes, gRes, engRes] = await Promise.allSettled([
          fetch(`${API_BASE}/api/timeline`).then((r) => r.json()),
          fetch(`${API_BASE}/jaya/api/v1/correlate/timeline`).then((r) =>
            r.json(),
          ),
          fetch(`${API_BASE}/jaya/api/v1/records/transactions`).then((r) =>
            r.json(),
          ),
          fetch(`${API_BASE}/jaya/api/v1/correlate/graph`).then((r) =>
            r.json(),
          ),
        ]);

        if (!isMounted) return;

        // Merge Manya's timeline + Jaya's uploaded SQLite events
        const manyaTl =
          tRes.status === "fulfilled" && tRes.value?.status === "success"
            ? tRes.value.data
            : { events: [], sessions: [], geo_tracks: [] };
        const jayaEvents =
          jayaTlRes.status === "fulfilled" &&
          Array.isArray(jayaTlRes.value?.events)
            ? jayaTlRes.value.events
            : [];

        setTimelineData({
          ...manyaTl,
          case_id: c.caseId,
          events: [...(manyaTl.events || []), ...jayaEvents],
        });

        if (gRes.status === "fulfilled") {
          const gData = gRes.value;
          setTransactionsData(Array.isArray(gData) ? gData : gData.items || []);
        }

        if (engRes.status === "fulfilled" && engRes.value?.nodes) {
          setEngineData(engRes.value);
        }
      } catch (err) {
        console.error("Data fetch error:", err);
      } finally {
        if (isMounted) setLoading(false);
      }
    };

    fetchData();
    return () => {
      isMounted = false;
    };
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
      </div>

      <nav className="subtabs">
        {TABS.map(([k, l]) => (
          <button
            key={k}
            className={"tab-btn" + (tab === k ? " active" : "")}
            onClick={() => setTab(k)}
          >
            {l}
          </button>
        ))}
      </nav>
      {tab === "overview" && (
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
              Upload Evidence
            </button>
          </div>
        </div>
      )}

      {tab === "graph" && (
        <div className="gt-split">
          <aside className="gt-left">
            <div className="gt-title">Timeline</div>
            {timelineData ? (
              <TimelineView data={timelineData} />
            ) : (
              <p className="muted p-4">No timeline data from backend.</p>
            )}
          </aside>
          <GraphView
            transactions={transactionsData}
            calls={[]}
            scores={{}}
            engine={engineData}
          />
        </div>
      )}

      {tab === "timeline" &&
        (timelineData ? (
          <TimelineView data={timelineData} />
        ) : (
          <p className="muted p-4">
            {loading ? "Loading Timeline..." : "No timeline data."}
          </p>
        ))}

      {tab === "map" &&
        (timelineData ? (
          <MapView data={timelineData} />
        ) : (
          <p className="muted p-4">
            {loading ? "Loading Map..." : "No map data."}
          </p>
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
    </div>
  );
}

function Theories({ c, user }) {
  return (
    <div className="panel">
      <h2 className="panel-title">Theories</h2>
      <p className="muted p-4">No theories added yet.</p>
    </div>
  );
}
