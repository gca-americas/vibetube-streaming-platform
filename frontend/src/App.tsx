import { useState, useEffect } from "react";
import { GatePage } from "./components/GatePage";
import { EventRoom } from "./components/EventRoom";
import { AdminPage } from "./components/AdminPage";
import { useRoute } from "./lib/router";

export default function App() {
  const route = useRoute();
  const [theme, setTheme] = useState<"dark" | "light">(() => {
    const saved = localStorage.getItem("theme");
    return (saved as "dark" | "light") || "dark";
  });

  // Sync theme changes with the DOM element class list
  useEffect(() => {
    if (theme === "light") {
      document.documentElement.classList.add("light");
    } else {
      document.documentElement.classList.remove("light");
    }
  }, [theme]);

  const toggleTheme = () => {
    const nextTheme = theme === "dark" ? "light" : "dark";
    setTheme(nextTheme);
    localStorage.setItem("theme", nextTheme);
  };

  // Unlinked on purpose: reachable only by typing /admin.
  if (route.name === "admin") {
    return <AdminPage theme={theme} onToggleTheme={toggleTheme} />;
  }

  if (route.name === "room") {
    return (
      <EventRoom
        // Remounts on code change so no state leaks between showrooms.
        key={route.code}
        code={route.code}
        theme={theme}
        onToggleTheme={toggleTheme}
      />
    );
  }

  return <GatePage theme={theme} onToggleTheme={toggleTheme} />;
}
