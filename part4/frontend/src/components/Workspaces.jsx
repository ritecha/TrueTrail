import { useState } from "react";
import { nameOf, knownUsers } from "../investigators.js";
import { createCase, unreadCount } from "../store.js";
import UploadCard from "./UploadCard.jsx";

export default function Workspaces({ user, cases, onOpen }) {
  const [creating, setCreating] = useState(false);
  const mine = cases.filter((c) => c.primary || c.members.includes(user.id)); // sample case is visible to every signed-in user

  return (
    <section>
      <h2 className="panel-title">Your cases</h2>
      <p className="muted small">Pick a case to open its workspace.</p>
      <div className="case-grid">
        {mine.map((c) => {
          const n = unreadCount(c, user.id);
          return (
            <button
              key={c.id}
              className="case-card neon-card"
              onClick={() => onOpen(c.id)}
            >
              <div className="case-top">
                <span className="case-id mono">{c.caseId}</span>
                <span
                  className={
                    "status-pill " + (c.status === "Active" ? "act" : "rev")
                  }
                >
                  {c.status}
                </span>
              </div>
              <h3>{c.name}</h3>
              <p className="muted small clamp">{c.desc}</p>
              <div className="case-foot">
                <div className="avatars">
                  {c.members.slice(0, 4).map((m) => (
                    <span
                      key={m}
                      className="avatar sm"
                      title={nameOf(m)}
                    >
                      {nameOf(m)[0]}
                    </span>
                  ))}
                </div>
                {n > 0 && <span className="badge">{n} new</span>}
              </div>
            </button>
          );
        })}
        <button
          className="case-card add-tile"
          onClick={() => setCreating(true)}
          title="Create my workspace"
          aria-label="Create my workspace"
        >
          <span className="plus">+</span>
        </button>
      </div>
      {creating && (
        <CreateModal
          user={user}
          onClose={() => setCreating(false)}
          onCreated={(c) => {
            setCreating(false);
            onOpen(c.id);
          }}
        />
      )}
    </section>
  );
}

function CreateModal({ user, onClose, onCreated }) {
  const [step, setStep] = useState(1);
  const [uploadedFiles, setUploadedFiles] = useState([]);
  const [f, setF] = useState({ name: "", desc: "" });
  const [members, setMembers] = useState([]);

  const toggle = (id) =>
    setMembers((m) =>
      m.includes(id) ? m.filter((x) => x !== id) : [...m, id],
    );

  const handleUploadDone = (data) => {
    setUploadedFiles((prev) => [...prev, data]);
  };

  const submit = (e) => {
    e.preventDefault();
    if (!f.name.trim() || uploadedFiles.length === 0) return;
    onCreated(
      createCase({
        ...f,
        owner: user.id,
        members,
        initialEvidence: uploadedFiles,
      }),
    );
  };

  return (
    <div className="drawer-back center" onClick={onClose}>
      <div
        className="modal neon-card"
        onClick={(e) => e.stopPropagation()}
        style={{ width: "550px", maxWidth: "90vw" }}
      >
        <h2 className="panel-title">Create New Workspace</h2>
        <p className="muted small">
          Step {step} of 2:{" "}
          {step === 1 ? "Upload Evidence" : "Workspace Details"}
        </p>

        {step === 1 && (
          <div style={{ marginTop: "20px" }}>
            <UploadCard actor={user.id} onDone={handleUploadDone} />
            <div
              className="modal-actions"
              style={{
                marginTop: "20px",
                display: "flex",
                justifyContent: "flex-end",
                gap: "10px",
              }}
            >
              <button type="button" className="mini" onClick={onClose}>
                Cancel
              </button>
              <button
                className="neon-btn"
                onClick={() => setStep(2)}
                disabled={uploadedFiles.length === 0}
              >
                Next: Details →
              </button>
            </div>
          </div>
        )}

        {step === 2 && (
          <form
            className="ws-form"
            onSubmit={submit}
            style={{ marginTop: "20px" }}
          >
            <label>Workspace Name *</label>
            <input
              value={f.name}
              onChange={(e) => setF({ ...f, name: e.target.value })}
              autoFocus
              required
            />

            <label>Description</label>
            <textarea
              rows="3"
              value={f.desc}
              onChange={(e) => setF({ ...f, desc: e.target.value })}
            />

            <label>Add Investigators</label>
            {knownUsers().filter((i) => i.id !== user.id).length === 0 && (
              <p className="muted small">
                Teammates appear here after they sign in on this device. Sharing a case across devices needs cases stored in Supabase.
              </p>
            )}
            <div className="pick">
              {knownUsers().filter((i) => i.id !== user.id).map((i) => (
                <label key={i.id} className="chk">
                  <input
                    type="checkbox"
                    checked={members.includes(i.id)}
                    onChange={() => toggle(i.id)}
                  />{" "}
                  {i.name}
                </label>
              ))}
            </div>

            <div
              className="modal-actions"
              style={{
                marginTop: "20px",
                display: "flex",
                justifyContent: "space-between",
              }}
            >
              <button type="button" className="mini" onClick={() => setStep(1)}>
                ← Back
              </button>
              <button
                className="neon-btn"
                type="submit"
                disabled={!f.name.trim()}
              >
                Create Workspace
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
