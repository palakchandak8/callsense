import { useEffect, useState } from "react";

function getInitialTheme() {
  try {
    const saved = localStorage.getItem("callsense-theme");
    if (saved === "light" || saved === "dark") return saved;
  } catch {}
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

export function useTheme() {
  const [theme, setTheme] = useState(getInitialTheme);

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    try {
      localStorage.setItem("callsense-theme", theme);
    } catch {}
  }, [theme]);

  return [theme, setTheme];
}

export default function ThemeToggle({ theme, setTheme }) {
  const isDark = theme === "dark";
  return (
    <button
      className="theme-toggle"
      onClick={() => setTheme(isDark ? "light" : "dark")}
      aria-label="Toggle dark mode"
      title={isDark ? "Switch to light mode" : "Switch to dark mode"}
    >
      {isDark ? "🌙" : "☀️"}
    </button>
  );
}