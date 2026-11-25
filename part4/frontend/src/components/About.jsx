const POINTS = [
  ["Secure", "Every uploaded file is SHA-256 hashed and written to a hash-chained audit ledger, so any later edit is detectable."],
  ["Correlate", "Bank, UPI, call and IP records are linked into one graph to surface mule accounts, shared devices and the likely handler."],
  ["Reconstruct", "Timeline and map views rebuild what happened, when and where, with every fact tied to a source record."],
];

export default function About() {
  return (
    <section className="panel neon-card about">
      <h2 className="panel-title">About TrueTrail</h2>
      <p className="about-lead">
        TrueTrail is a digital-evidence engine for cyber-fraud investigations. It keeps evidence
        tamper-evident, connects scattered records into a single picture, and helps investigators
        explain their findings with traceable sources.
      </p>
      <div className="about-grid">
        {POINTS.map(([t, d]) => (
          <div key={t} className="about-item"><h3>{t}</h3><p className="muted">{d}</p></div>
        ))}
      </div>
      <p className="muted small">Patterns surfaced by the tool are leads for investigators, not proof. Access is restricted to registered investigators.</p>
    </section>
  );
}
