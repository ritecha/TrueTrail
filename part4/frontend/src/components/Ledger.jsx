import { useEffect, useState } from "react";

// export const API = import.meta.env.VITE_API_URL ?? "http://localhost:8001";
// const API = import.meta.env.VITE_API_URL || "http://localhost:8001";
export const API = "https://digitalevidencebytruetrail-backend.onrender.com";

// Chain of custody table + per-file verify
export default function Ledger({ refreshKey }) {
  const [rows, setRows] = useState([]);
  const [chain, setChain] = useState(null);
  const [offline, setOffline] = useState(false);
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
    </div>
  );
}
