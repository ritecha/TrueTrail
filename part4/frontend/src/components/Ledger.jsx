import { useEffect, useState } from "react";

// export const API = import.meta.env.VITE_API_URL ?? "http://localhost:8001";
// const API = import.meta.env.VITE_API_URL || "http://localhost:8001";
const API = "https://digitalevidencebytruetrail-backend.onrender.com";
// Chain of custody table + per-file verify + BSA Section 63 certificate download
export default function Ledger({ refreshKey }) {
  const [rows, setRows] = useState([]);
  const [chain, setChain] = useState(null);
  const [offline, setOffline] = useState(false);
  const [caseId, setCaseId] = useState("CR-2026-001");
  const [checks, setChecks] = useState({}); // file -> verify result

  const load = async () => {
    try {
      const a = await fetch(`${API}/audit`);
      if (!a.ok) throw new Error();
      setRows(await a.json());
      setChain(await (await fetch(`${API}/audit/verify`)).json());
      setOffline(false);
    } catch {
      setOffline(true);
    }
  };
  useEffect(() => {
    load();
  }, [refreshKey]);

  const verifyFile = async (name) => {
    try {
      const r = await fetch(
        `${API}/evidence/${encodeURIComponent(name)}/verify`,
      );
      if (!r.ok) throw new Error();
      const result = await r.json();
      setChecks((c) => ({ ...c, [name]: result }));
      load();
    } catch {
      setChecks((c) => ({ ...c, [name]: { error: true } }));
    }
  };

  const certificate = async (row) => {
    const q = new URLSearchParams({
      file_name: row.file ?? row.file_name,
      file_hash: row.file_hash,
      case_id: caseId,
    });
    try {
      const r = await fetch(`${API}/report?${q}`, { method: "POST" });
      if (!r.ok) throw new Error();
      const url = URL.createObjectURL(await r.blob());
      const a = document.createElement("a");
      a.href = url;
      a.download = `BSA_${caseId}.pdf`;
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      alert(
        "Could not generate the PDF. Is the backend (port 8001) running with the /report endpoint?",
      );
    }
  };

  const ingests = rows.filter((r) => r.action === "INGEST");
  return (
    <div className="panel neon-card">
      <h2 className="panel-title">Chain of custody</h2>
      <div
        className={"status " + (offline ? "warn" : chain?.valid ? "ok" : "bad")}
      >
        {offline
          ? "Backend offline. Start the API on port 8001."
          : chain?.valid
            ? `Ledger intact · ${chain.entries} entries, every hash links to the previous one`
            : `Ledger broken at entry ${chain?.broken_at_entry ?? "?"}. Something was edited after it was recorded.`}
      </div>

      <table className="audit-table">
        <thead>
          <tr>
            <th>#</th>
            <th>Time (UTC)</th>
            <th>Action</th>
            <th>File</th>
            <th>SHA-256</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 && (
            <tr>
              <td colSpan="6" className="empty">
                No evidence yet. Upload a file from the card above.
              </td>
            </tr>
          )}
          {rows.map((r) => {
            const name = r.file ?? r.file_name;
            const c = checks[name];
            return (
              <tr key={r.id}>
                <td>{r.id}</td>
                <td className="mono">
                  {String(r.ts).slice(0, 19).replace("T", " ")}
                </td>
                <td>{r.action}</td>
                <td>{name}</td>
                <td className="mono" title={r.file_hash}>
                  {r.file_hash?.slice(0, 16)}…
                </td>
                <td className="actions">
                  {r.action === "INGEST" && (
                    <>
                      <button className="mini" onClick={() => verifyFile(name)}>
                        Verify file
                      </button>
                      {c && !c.error && (
                        <span className={c.match ? "tag ok" : "tag bad"}>
                          {c.match ? "unchanged" : "MODIFIED"}
                        </span>
                      )}
                      {c?.error && (
                        <span className="tag bad">file not found</span>
                      )}
                    </>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>

      <div className="cert">
        <div>
          <h3>Court certificate (BSA 2023, Section 63)</h3>
          <p className="muted">Generates a PDF for a file in the ledger.</p>
        </div>
        <input
          value={caseId}
          onChange={(e) => setCaseId(e.target.value)}
          placeholder="Case ID"
        />
        <button
          className="neon-btn"
          disabled={!ingests.length}
          onClick={() => certificate(ingests[ingests.length - 1])}
        >
          Download for latest upload
        </button>
      </div>
    </div>
  );
}
