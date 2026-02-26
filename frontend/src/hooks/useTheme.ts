import { useEffect, useCallback, useState } from "react";
import { STORAGE_KEY_MODE, STORAGE_KEY_PALETTE } from "../constants";

export type Mode = "dark" | "light";
export type Palette =
  | "default"
  | "pink"
  | "ocean"
  | "forest"
  | "sunset"
  | "mono"
  | "neon"
  | "slate"
  | "rosegold";

export interface ThemeState {
  mode: Mode;
  palette: Palette;
}

const VALID_MODES: Mode[] = ["dark", "light"];
const VALID_PALETTES: Palette[] = [
  "default", "pink", "ocean", "forest", "sunset", "mono", "neon", "slate", "rosegold",
];

function readTheme(): ThemeState {
  const rawMode = localStorage.getItem(STORAGE_KEY_MODE) as Mode | null;
  const rawPalette = localStorage.getItem(STORAGE_KEY_PALETTE) as Palette | null;
  return {
    mode: rawMode && VALID_MODES.includes(rawMode) ? rawMode : "dark",
    palette: rawPalette && VALID_PALETTES.includes(rawPalette) ? rawPalette : "default",
  };
}

function applyToDocument(t: ThemeState) {
  document.documentElement.setAttribute("data-mode", t.mode);
  document.documentElement.setAttribute("data-palette", t.palette);
}

export function useTheme() {
  const [theme, setTheme] = useState<ThemeState>(readTheme);

  useEffect(() => {
    applyToDocument(theme);
  }, [theme]);

  const toggleMode = useCallback(() => {
    setTheme((prev) => {
      const next: ThemeState = {
        ...prev,
        mode: prev.mode === "dark" ? "light" : "dark",
      };
      localStorage.setItem(STORAGE_KEY_MODE, next.mode);
      return next;
    });
  }, []);

  const setPalette = useCallback((p: Palette) => {
    setTheme((prev) => {
      const next: ThemeState = { ...prev, palette: p };
      localStorage.setItem(STORAGE_KEY_PALETTE, next.palette);
      return next;
    });
  }, []);

  return { theme, toggleMode, setPalette };
}
