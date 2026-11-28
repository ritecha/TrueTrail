import { useEffect, useState, useRef } from "react";
import { API } from "./Ledger.jsx";

const ACCEPTED = ".csv,.xlsx,.xls,.json,.pdf,.png,.jpg,.jpeg";

export default function UploadCard({ actor, onDone, caseId = "c1" }) {
  const [files, setFiles] = useState([]);
  const [db, setDb] = useState("checking");
  const [uploading, setUploading] = useState(false);
  const [lastMsg, setLastMsg] = useState("");
  const fileInputRef = useRef(null);

  useEffect(() => {
    let live = true;
    fetch(`${API}/jaya/health`)
      .then((r) => live && setDb(r.ok ? "online" : "offline"))
      .catch(() => live && setDb("offline"));
    return () => {
      live = false;
    };
  }, [files]);

  const handleDrop = (e) => {
    e.preventDefault();
    setLastMsg("");
    addFiles(Array.from(e.dataTransfer.files));
  };

  const handleSelect = (e) => {
    setLastMsg("");
    addFiles(Array.from(e.target.files));
  };

  const addFiles = (newFiles) => {
    const formatted = newFiles.map((f) => ({
      id: Math.random().toString(36).slice(2, 11),
      file: f,
      status: "pending",
      progress: 0,
    }));
    setFiles((prev) => [...prev, ...formatted]);
  };

  const uploadAll = async () => {
    const pendingFiles = files.filter(
      (f) => f.status === "pending" || f.status === "failed",
    );
    if (pendingFiles.length === 0 || uploading) return;

    setUploading(true);
    setLastMsg("");
    let successCount = 0;

    for (const item of pendingFiles) {
      setFiles((prev) =>
        prev.map((f) => (f.id === item.id ? { ...f, status: "uploading" } : f)),
      );

      try {
        const body = new FormData();
        body.append("file", item.file);
        body.append("uploaded_by", actor || "investigator");
        body.append("case_id", caseId);
        body.append("sync", "false");

        const r = await fetch(`${API}/jaya/api/v1/evidence/upload`, {
          method: "POST",
          body,
        });

        if (!r.ok) {
          const errData = await r.json().catch(() => ({}));
          throw new Error(errData.detail || "Upload failed");
        }

        const d = await r.json();
        successCount++;

        onDone?.({
          ...d,
          file:
            d.file ||
            d.filename ||
            d.evidence?.original_filename ||
            item.file.name,
        });
      } catch (err) {
        console.error("Upload Error:", err);
        setFiles((prev) =>
          prev.map((f) => (f.id === item.id ? { ...f, status: "failed" } : f)),
        );
      }
    }

    // Reset queue & input so the user can upload again immediately
    if (successCount === pendingFiles.length) {
      setFiles([]);
      setLastMsg(`Uploaded ${successCount} file(s). Ready for more.`);
    } else if (successCount > 0) {
      setFiles((prev) => prev.filter((f) => f.status === "failed"));
      setLastMsg(`Uploaded ${successCount} file(s); some failed.`);
    }
    if (fileInputRef.current) fileInputRef.current.value = "";
    setUploading(false);
  };

  return (
    <div className="upload-card">
      <div className="upload-head">
        <h4>INGEST EVIDENCE</h4>
        <span
          className={"dbdot " + db}
          style={{
            color: db === "online" ? "var(--risk-low)" : "var(--risk-high)",
          }}
        >
          {db === "online"
            ? "● Backend Connected"
            : db === "offline"
              ? "○ Offline"
              : "Connecting…"}
        </span>
      </div>

      <div
        className="drop"
        onClick={() => fileInputRef.current?.click()}
        onDragOver={(e) => e.preventDefault()}
        onDrop={handleDrop}
        style={{
          cursor: "pointer",
          minHeight: "80px",
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          border: "1px dashed var(--border-strong)",
          borderRadius: "6px",
          background: "var(--bg-base)",
        }}
      >
        <span style={{ fontSize: "20px", marginBottom: "4px", opacity: 0.7 }}>
          📁
        </span>
        <span
          className="muted small"
          style={{ textAlign: "center", fontSize: "11px" }}
        >
          Click or drag files
          <br />({ACCEPTED})
        </span>
      </div>
      <input
        type="file"
        ref={fileInputRef}
        style={{ display: "none" }}
        onChange={handleSelect}
        multiple
        accept={ACCEPTED}
      />

      {lastMsg && (
        <div
          className="small"
          style={{ marginTop: "8px", color: "var(--risk-low)" }}
        >
          {lastMsg}
        </div>
      )}

      {files.length > 0 && (
        <div
          style={{ marginTop: "12px", maxHeight: "150px", overflowY: "auto" }}
        >
          {files.map((f) => {
            const ext = f.file.name.split(".").pop().toUpperCase();
            return (
              <div
                key={f.id}
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  padding: "8px 0",
                  borderBottom: "1px solid var(--border-subtle)",
                  fontSize: "12px",
                }}
              >
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: "8px",
                    overflow: "hidden",
                  }}
                >
                  <span
                    style={{
                      background: "var(--bg-hover)",
                      padding: "2px 6px",
                      borderRadius: "4px",
                      fontSize: "10px",
                      color: "var(--text-muted)",
                    }}
                  >
                    {ext}
                  </span>
                  <span
                    style={{
                      textOverflow: "ellipsis",
                      overflow: "hidden",
                      whiteSpace: "nowrap",
                      maxWidth: "120px",
                    }}
                  >
                    {f.file.name}
                  </span>
                </div>
                <div>
                  {f.status === "pending" && (
                    <span className="muted">Pending</span>
                  )}
                  {f.status === "uploading" && (
                    <span style={{ color: "var(--risk-med)" }}>Uploading…</span>
                  )}
                  {f.status === "failed" && (
                    <span style={{ color: "var(--risk-high)" }}>Failed</span>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}

      <button
        className="neon-btn"
        onClick={uploadAll}
        style={{ marginTop: "12px", width: "100%" }}
        disabled={files.length === 0 || uploading}
      >
        {uploading ? "Uploading…" : "Upload Files"}
      </button>
    </div>
  );
}
