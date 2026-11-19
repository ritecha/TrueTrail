import { useMemo, useState } from "react";
import "./App.css";
import ReactLenis from "lenis/react";
import RippleBackground from "./RippleBackground.jsx";
import SkiperText from "./SkiperText.jsx";
import Ledger from "./components/Ledger.jsx";
import GraphView from "./components/GraphView.jsx";
import { TimelineView, MapView } from "./components/TimeMap.jsx";
import timeline from "./timeline.json";
import transactions from "./transactions.json";
import calls from "./calls.json";
import engineScores from "./engineScores.json";
import engineGraph from "./engineGraph.json";
import BeeScroll from "./components/BeeScroll.jsx";
import "./effects.css";
import TiltCard from "./components/TiltCard.jsx";
const TABS = ["dashboard", "graph", "timeline", "map"];
// const API = import.meta.env.VITE_API_URL || "http://localhost:8001";
const API = "https://digitalevidencebytruetrail-backend.onrender.com";
export default function App() {
  const [tab, setTab] = useState("dashboard");
  const [file, setFile] = useState(null);
  const [status, setStatus] = useState("");
  const [refreshKey, setRefreshKey] = useState(0);
  const txns = useMemo(() => transactions, []);

  const upload = async () => {
    if (!file) return setStatus("Choose a file first.");
    const body = new FormData();
    body.append("file", file);
    try {
      setStatus("Hashing…");
      const r = await fetch(`${API}/evidence/upload`, { method: "POST", body });
      if (!r.ok) throw new Error();
      const d = await r.json();
      setStatus(`Recorded · ${d.sha256.slice(0, 16)}…`);
      setRefreshKey((k) => k + 1);
    } catch {
      setStatus("Backend not reachable (port 8001).");
    }
  };

  return (
    <ReactLenis root>
      <RippleBackground />
      <div className="page">
        <div className="hero-row">
          <TiltCard className="ingest-card">
            <h2>TRUETRAIL</h2>
            <p className="sub">EVIDENCE ENGINE</p>
            <div className="ingest-box">
              <h4>INGEST EVIDENCE</h4>
              <input type="file" onChange={(e) => setFile(e.target.files[0])} />
              <button className="neon-btn" onClick={upload}>
                Upload & Hash
              </button>
              {status && <p className="ingest-status">{status}</p>}
            </div>
          </TiltCard>
          <div className="hero-text">
            <h1>Digital Evidence Correlation</h1>
            <p>Secure. Correlate. Reconstruct.</p>
          </div>
        </div>

        <div className="stage">
          <SkiperText />
          <BeeScroll />
        </div>

        <nav className="tabs" aria-label="Sections">
          {TABS.map((t) => (
            <button
              key={t}
              className={"tab-btn" + (tab === t ? " active" : "")}
              onClick={() => setTab(t)}
            >
              {t}
            </button>
          ))}
        </nav>

        {tab === "dashboard" && <Ledger refreshKey={refreshKey} />}
        {tab === "graph" && (
          <GraphView
            transactions={txns}
            calls={calls}
            scores={engineScores}
            engine={engineGraph}
          />
        )}
        {tab === "timeline" && <TimelineView data={timeline} />}
        {tab === "map" && <MapView data={timeline} />}
      </div>
    </ReactLenis>
  );
}
