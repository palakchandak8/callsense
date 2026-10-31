import { useState } from "react";
import "./App.css";
import LiveCall from "./screens/LiveCall";
import Dashboard from "./screens/Dashboard";
import MindMap from "./screens/MindMap";
import ThemeToggle, { useTheme } from "./components/ThemeToggle";

const SCREENS = {
  call: { label: "Live Call", component: LiveCall },
  dashboard: { label: "Dashboard", component: Dashboard },
  mindmap: { label: "Mind Map", component: MindMap },
};

function App() {
  const [screen, setScreen] = useState("call");
  const [theme, setTheme] = useTheme();
  const Active = SCREENS[screen].component;

  return (
    <div className="app">
      <header className="nav">
        <span className="brand">CallSense</span>
        <nav>
          {Object.entries(SCREENS).map(([key, { label }]) => (
            <button
              key={key}
              className={screen === key ? "nav-btn active" : "nav-btn"}
              onClick={() => setScreen(key)}
            >
              {label}
            </button>
          ))}
          <ThemeToggle theme={theme} setTheme={setTheme} />
        </nav>
      </header>
      <main>
        <Active />
      </main>
    </div>
  );
}

export default App;