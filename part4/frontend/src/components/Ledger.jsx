import { useEffect, useState } from "react";

export const API = "https://digitalevidencebytruetrail-backend.onrender.com";
export default function Ledger({ refreshKey }) {
  const [rows, setRows] = useState([]);
  const [offline, setOffline] = useState(false);
  const [checks, setChecks] = useState({});

  const load = async () => {
    try {
      const r = await fetch(`${API}/jaya/api/v1/evidence`);
      if (!r.ok) throw new Error();
      const d = await r.json();
      setRows(Array.isArray(d.items) ? d.items : []);
      setOffline(false);
    } catch {
      setOffline(true);
    }
  };

  useEffect(() => {
    load();
  }, [refreshKey]);

  const verifyFile = async (evidenceId) => {
    try {
      const r = await fetch(
        `${API}/jaya/api/v1/evidence/${encodeURIComponent(evidenceId)}/verify`,
      );
      if (!r.ok) throw new Error();
      const result = await r.json();
      setChecks((c) => ({ ...c, [evidenceId]: result }));
    } catch {
      setChecks((c) => ({ ...c, [evidenceId]: { error: true } }));
    }
  };

  return (
    <div className="panel neon-card">
      <h2 className="panel-title">Chain of custody</h2>
      <div className={"status " + (offline ? "warn" : "ok")}>
        {offline
          ? "Backend offline. Check VITE_API_URL or start the API on port 8001."
          : `Vault connected · ${rows.length} preserved evidence item(s)`}
      </div>

      <table className="audit-table">
        <thead>
          <tr>
            <th>ID</th>
            <th>Time (UTC)</th>
            <th>Type</th>
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
            const id = r.evidence_id;
            const name = r.original_filename;
            const hash = r.sha256_hash;
            const c = checks[id];
            const ok = c && !c.error && (c.verified ?? c.match ?? c.intact);
            return (
              <tr key={id}>
                <td className="mono">{String(id).slice(0, 10)}</td>
                <td className="mono">
                  {String(r.ingested_at || "")
                    .slice(0, 19)
                    .replace("T", " ")}
                </td>
                <td>{r.evidence_type || "INGEST"}</td>
                <td>{name}</td>
                <td className="mono" title={hash}>
                  {hash?.slice(0, 16)}…
                </td>
                <td className="actions">
                  <button className="mini" onClick={() => verifyFile(id)}>
                    Verify file
                  </button>
                  {c && !c.error && (
                    <span className={ok ? "tag ok" : "tag bad"}>
                      {ok ? "unchanged" : "MODIFIED"}
                    </span>
                  )}
                  {c?.error && <span className="tag bad">file not found</span>}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
