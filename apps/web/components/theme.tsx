"use client";

import { Moon, Sun } from "lucide-react";
import { useCallback, useSyncExternalStore } from "react";
import { Button } from "@/components/ui/button";

export type Theme = "dark" | "light";
const KEY = "unlink.theme";

/** Runs before paint (inlined in <head>) so the page never flashes the wrong theme. Dark is the default. */
export const THEME_SCRIPT = `(function(){try{var t=localStorage.getItem("${KEY}");var d=t?t==="dark":true;var c=document.documentElement.classList;c.toggle("dark",d);c.toggle("light",!d);}catch(e){}})();`;

function subscribe(cb: () => void) {
  const obs = new MutationObserver(cb);
  obs.observe(document.documentElement, { attributes: true, attributeFilter: ["class"] });
  return () => obs.disconnect();
}

export function useTheme() {
  const theme = useSyncExternalStore<Theme>(
    subscribe,
    () => (document.documentElement.classList.contains("dark") ? "dark" : "light"),
    () => "dark",
  );
  const setTheme = useCallback((t: Theme) => {
    const c = document.documentElement.classList;
    c.toggle("dark", t === "dark");
    c.toggle("light", t === "light");
    try {
      localStorage.setItem(KEY, t);
    } catch {}
  }, []);
  return { theme, setTheme, toggle: () => setTheme(theme === "dark" ? "light" : "dark") };
}

export function ThemeToggle({ className }: { className?: string }) {
  const { theme, toggle } = useTheme();
  return (
    <Button variant="ghost" size="icon" className={className} onClick={toggle}
            aria-label={theme === "dark" ? "Switch to light theme" : "Switch to dark theme"}>
      {theme === "dark" ? <Sun className="size-4" /> : <Moon className="size-4" />}
    </Button>
  );
}
