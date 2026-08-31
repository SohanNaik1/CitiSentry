"use client";

import { useTheme } from "next-themes";
import { useEffect, useState } from "react";
import { Sun, Moon } from "lucide-react";

export function ThemeToggle() {
  const { theme, setTheme } = useTheme();
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  if (!mounted) {
    return <div className="w-8 h-8" />; // Placeholder to prevent layout shift
  }

  return (
    <button
      onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
      className="relative p-2 rounded-full bg-slate-200 dark:bg-zinc-800 border border-slate-300 dark:border-zinc-700 text-slate-700 dark:text-zinc-300 transition-all hover:bg-slate-300 dark:hover:bg-zinc-700"
      aria-label="Toggle Dark Mode"
    >
      <div className="absolute inset-0 rounded-full bg-gradient-to-tr from-cyan-telemetry/20 to-emerald-online/20 blur-[2px] opacity-0 dark:opacity-100 transition-opacity"></div>
      <div className="relative z-10 flex items-center justify-center">
        {theme === "dark" ? (
          <Sun className="w-4 h-4" />
        ) : (
          <Moon className="w-4 h-4" />
        )}
      </div>
    </button>
  );
}
