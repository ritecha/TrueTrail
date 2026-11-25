import { useState, useEffect } from "react";
import "./App.css";
import ReactLenis from "lenis/react";
import RippleBackground from "./RippleBackground.jsx";
import "./effects.css";
import AgentChat from "./components/AgentChat.jsx";
import "./agent.css";
import "./ui.css";
import "./theme.css"; // keep LAST so it wins over the older css files
import Header from "./components/Header.jsx";
import About from "./components/About.jsx";
import Workspaces from "./components/Workspaces.jsx";
import WorkspaceView from "./components/WorkspaceView.jsx";
import { useCases } from "./store.js";

// 🔐 Clerk Imports
import { useUser, SignIn } from "@clerk/react";
import { rememberUser } from "./investigators.js";

export default function App() {
  // 🔐 Clerk Hooks
  const { isLoaded, isSignedIn, user } = useUser();

  // App State
  const [view, setView] = useState("cases"); // cases | case | about
  const [caseId, setCaseId] = useState(null);
  const [agentOpen, setAgentOpen] = useState(false);
  const cases = useCases();
  const active = cases.find((c) => c.id === caseId);

  // 🌗 Theme State
  const [theme, setTheme] = useState(localStorage.getItem("theme") || "dark");

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem("theme", theme);
  }, [theme]);

  const toggleTheme = () => setTheme(theme === "dark" ? "light" : "dark");

  // 1. Loading State
  if (!isLoaded) {
    return (
      <div
        className="page"
        style={{
          display: "flex",
          justifyContent: "center",
          alignItems: "center",
          height: "100vh",
        }}
      >
        Loading authentication...
      </div>
    );
  }

  // 2. Not Signed In State (Clerk Login Screen)
  if (!isSignedIn) {
    return (
      <ReactLenis root>
        <RippleBackground />
        <div
          style={{
            display: "flex",
            justifyContent: "center",
            alignItems: "center",
            height: "100vh",
          }}
        >
          <SignIn routing="hash" />
        </div>
      </ReactLenis>
    );
  }

  // 3. Map Clerk User to Your App's User Format
  const appUser = {
    id: user.id,
    name: user.fullName || user.firstName || "Investigator",
  };

  rememberUser(appUser.id, appUser.name);

  const open = (id) => {
    setCaseId(id);
    setView("case");
    window.scrollTo(0, 0);
  };

  // 4. Main App (Signed In)
  return (
    <ReactLenis root>
      <RippleBackground />

      <Header
        view={view}
        setView={(v) => setView(v)}
        user={appUser}
        theme={theme}
        onToggleTheme={toggleTheme}
        onAsk={() => setAgentOpen(true)}
      />

      <div className="page">
        {view === "cases" && (
          <Workspaces user={appUser} cases={cases} onOpen={open} />
        )}
        {view === "case" && active && (
          <WorkspaceView
            key={active.id}
            c={active}
            user={appUser}
            onBack={() => setView("cases")}
          />
        )}
        {view === "about" && <About />}
      </div>

      {agentOpen && (
        <div className="drawer-back" onClick={() => setAgentOpen(false)}>
          <aside className="drawer" onClick={(e) => e.stopPropagation()}>
            <button
              className="drawer-x"
              onClick={() => setAgentOpen(false)}
              aria-label="Close"
            >
              ✕
            </button>
            {active ? (
              <AgentChat key={active.id} user={appUser} c={active} />
            ) : (
              <div className="panel neon-card agent">
                <h2 className="panel-title">Case assistant</h2>
                <p className="muted">
                  Open a case first. The assistant answers only about the case
                  you are in.
                </p>
              </div>
            )}
          </aside>
        </div>
      )}
    </ReactLenis>
  );
}
