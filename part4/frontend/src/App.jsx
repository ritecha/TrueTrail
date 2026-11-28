import { useState, useEffect } from "react";
import "./App.css";
import ReactLenis from "lenis/react";
import RippleBackground from "./RippleBackground.jsx";
import "./effects.css";
import "./agent.css";
import "./ui.css";
import "./theme.css";
import Header from "./components/Header.jsx";
import About from "./components/About.jsx";
import Workspaces from "./components/Workspaces.jsx";
import WorkspaceView from "./components/WorkspaceView.jsx";
import { useCases } from "./store.js";

import { useUser, SignIn } from "@clerk/react";
import { rememberUser } from "./investigators.js";

export default function App() {
  const { isLoaded, isSignedIn, user } = useUser();
  const [guest, setGuest] = useState(
    () => localStorage.getItem("truetrail.guest") === "1",
  );

  const [view, setView] = useState("cases");
  const [caseId, setCaseId] = useState(null);
  const cases = useCases();
  const active = cases.find((c) => c.id === caseId);

  const [theme, setTheme] = useState(localStorage.getItem("theme") || "dark");

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem("theme", theme);
  }, [theme]);

  const toggleTheme = () => setTheme(theme === "dark" ? "light" : "dark");

  if (!isLoaded && !guest) {
    return (
      <div
        className="page"
        style={{
          display: "flex",
          flexDirection: "column",
          gap: "12px",
          justifyContent: "center",
          alignItems: "center",
          height: "100vh",
        }}
      >
        <span>Loading authentication...</span>
        <button
          className="mini"
          onClick={() => {
            localStorage.setItem("truetrail.guest", "1");
            setGuest(true);
          }}
        >
          Continue as Guest (Demo)
        </button>
      </div>
    );
  }

  if (!isSignedIn && !guest) {
    return (
      <ReactLenis root>
        <RippleBackground />
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            gap: "16px",
            justifyContent: "center",
            alignItems: "center",
            minHeight: "100vh",
            padding: "20px",
          }}
        >
          <SignIn routing="hash" fallbackRedirectUrl="/" forceRedirectUrl="/" />
          <button
            className="neon-btn"
            onClick={() => {
              localStorage.setItem("truetrail.guest", "1");
              setGuest(true);
            }}
          >
            Continue as Guest (No Login)
          </button>
        </div>
      </ReactLenis>
    );
  }

  const appUser =
    isSignedIn && user
      ? {
          id: user.id,
          name: user.fullName || user.firstName || "Investigator",
        }
      : {
          id: "guest.demo",
          name: "Demo Investigator",
        };

  rememberUser(appUser.id, appUser.name);

  const open = (id) => {
    setCaseId(id);
    setView("case");
    window.scrollTo(0, 0);
  };

  return (
    <ReactLenis root>
      <RippleBackground />

      <Header
        view={view}
        setView={(v) => setView(v)}
        user={appUser}
        theme={theme}
        onToggleTheme={toggleTheme}
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
    </ReactLenis>
  );
}
