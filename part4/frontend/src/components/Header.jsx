import { UserButton } from "@clerk/react";

const ICON = {
  cases:
    "M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z",
  about: "M12 8h.01M11 12h1v5h1M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18z",
  sun: "M12 17a5 5 0 1 0 0-10 5 5 0 0 0 0 10zM12 1v2M12 21v2M4.2 4.2l1.4 1.4M18.4 18.4l1.4 1.4M1 12h2M21 12h2M4.2 19.8l1.4-1.4M18.4 5.6l1.4-1.4",
  moon: "M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z",
};
const Icon = ({ d }) => (
  <svg
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="1.7"
    strokeLinecap="round"
    strokeLinejoin="round"
    aria-hidden="true"
  >
    <path d={d} />
  </svg>
);
const LINKS = [
  ["cases", "Cases"],
  ["about", "About"],
];

export default function Header({ view, setView, user, theme, onToggleTheme }) {
  const active = view === "case" ? "cases" : view;
  return (
    <aside className="rail" aria-label="Main">
      <button
        className="rail-logo"
        onClick={() => setView("cases")}
        title="TrueTrail"
      >
        <b>TT</b>
        <span>
          TRUE<i>TRAIL</i>
        </span>
      </button>
      {LINKS.map(([k, label]) => (
        <button
          key={k}
          className={"rail-item" + (active === k ? " on" : "")}
          onClick={() => setView(k)}
          title={label}
        >
          <Icon d={ICON[k]} />
          <span className="lbl">{label}</span>
        </button>
      ))}
      <div className="rail-space" />
      <button
        className="rail-item"
        onClick={onToggleTheme}
        title="Switch theme"
        aria-label="Switch between dark and light theme"
      >
        <Icon d={theme === "dark" ? ICON.sun : ICON.moon} />
        <span className="lbl">
          {theme === "dark" ? "Light mode" : "Dark mode"}
        </span>
      </button>
      <div className="rail-user">
        <span className="rail-avatar">
          <UserButton afterSignOutUrl="/" />
        </span>
        <span className="who-txt">{user.name}</span>
      </div>
    </aside>
  );
}
