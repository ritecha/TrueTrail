import { useEffect, useState, useRef } from "react";
import { API } from "./Ledger.jsx";
import { createClient } from "@supabase/supabase-js";

const ACCEPTED = ".csv,.xlsx,.xls,.json,.pdf,.png,.jpg,.jpeg";
import { supabase } from "../supabaseClient";

export default function UploadCard({ actor, onDone }) {
  const [files, setFiles] = useState([]);
  const [db, setDb] = useState("checking");
  const fileInputRef = useRef(null);

  useEffect(() => {
    let live = true;
    // Check Supabase first, then fallback to FastAPI
    if (supabase) {
      setDb("online");
    } else {
      fetch(`${API}/audit/verify`)
        .then((r) => live && setDb(r.ok ? "online" : "offline"))
        .catch(() => live && setDb("offline"));
    }
    return () => {
      live = false;
    };
  }, [files]);

  const handleDrop = (e) => {
    e.preventDefault();
    addFiles(Array.from(e.dataTransfer.files));
  };

  const handleSelect = (e) => addFiles(Array.from(e.target.files));

  const addFiles = (newFiles) => {
    const formatted = newFiles.map((f) => ({
      id: Math.random().toString(36).substr(2, 9),
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
    if (pendingFiles.length === 0) return;

    for (let item of pendingFiles) {
      setFiles((prev) =>
        prev.map((f) => (f.id === item.id ? { ...f, status: "uploading" } : f)),
      );

      try {
        if (supabase) {
          // 🔥 Supabase Upload Logic
          const fileExt = item.file.name.split(".").pop();
          const fileName = `${Date.now()}-${Math.random().toString(36).substring(7)}.${fileExt}`;
          const { data, error } = await supabase.storage
            .from("evidence")
            .upload(fileName, item.file);

          if (error) throw error;

          // Save metadata to DB (Assuming a 'files' table exists)
          await supabase.from("files").insert([
            {
              filename: item.file.name,
              storage_path: fileName,
              uploaded_by: actor,
            },
          ]);

          const mockResponse = {
            file: item.file.name,
            sha256: "supabase_hash_" + Date.now(),
          };
          setFiles((prev) =>
            prev.map((f) =>
              f.id === item.id ? { ...f, status: "parsed", progress: 100 } : f,
            ),
          );
          onDone?.(mockResponse);
        } else {
          // Fallback to FastAPI
          const body = new FormData();
          body.append("file", item.file);
          const r = await fetch(
            `${API}/evidence/upload?actor=${encodeURIComponent(actor)}`,
            { method: "POST", body },
          );
          if (!r.ok) throw new Error();
          const d = await r.json();
          setFiles((prev) =>
            prev.map((f) =>
              f.id === item.id ? { ...f, status: "parsed", progress: 100 } : f,
            ),
          );
          onDone?.(d);
        }
      } catch (err) {
        console.error(err);
        setFiles((prev) =>
          prev.map((f) => (f.id === item.id ? { ...f, status: "failed" } : f)),
        );
      }
    }
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
            ? supabase
              ? "● Supabase Connected"
              : "● Backend Connected"
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
                    <span style={{ color: "var(--risk-med)" }}>Hashing…</span>
                  )}
                  {f.status === "parsed" && (
                    <span style={{ color: "var(--risk-low)" }}>Parsed</span>
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
        disabled={files.length === 0}
      >
        Upload Files
      </button>
    </div>
  );
}
