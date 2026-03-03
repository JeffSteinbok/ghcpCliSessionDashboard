/**
 * Hamburger menu (☰) — dropdown in the header-right area, next to
 * the timestamp.
 *
 * Contains:
 *   - "Start on login" toggle (hidden when platform doesn't support it)
 *   - "Remote sync" toggle (enables/disables OneDrive sync)
 *   - Divider
 *   - "About" link → GitHub repo (replaces old "What is this?")
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { useAutostart, useSettings } from "../hooks";

export default function HamburgerMenu() {
  const [open, setOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  const autostart = useAutostart();
  const { settings, loading: settingsLoading, setSyncEnabled } = useSettings();

  const toggle = useCallback(() => setOpen((prev) => !prev), []);

  // Close on outside click
  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  // Close on Escape
  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [open]);

  return (
    <div className="hamburger-wrapper" ref={menuRef}>
      <button
        className="hamburger-btn"
        onClick={toggle}
        title="Settings"
        aria-label="Open settings menu"
        aria-expanded={open}
      >
        ☰
      </button>

      {open && (
        <div className="hamburger-dropdown" role="menu">
          {/* Autostart toggle — only shown when platform supports it */}
          {autostart.supported && (
            <label className="hamburger-item hamburger-toggle" role="menuitem">
              <span>Start on login</span>
              <input
                type="checkbox"
                checked={autostart.enabled}
                disabled={autostart.toggling}
                onChange={(e) => autostart.toggle(e.target.checked)}
              />
              <span className="toggle-slider" />
            </label>
          )}

          {/* Remote sync toggle */}
          {!settingsLoading && (
            <label className="hamburger-item hamburger-toggle" role="menuitem">
              <span>Remote sync</span>
              <input
                type="checkbox"
                checked={settings.sync_enabled}
                onChange={(e) => setSyncEnabled(e.target.checked)}
              />
              <span className="toggle-slider" />
            </label>
          )}

          <div className="hamburger-divider" />

          {/* About link */}
          <a
            className="hamburger-item"
            href="https://github.com/JeffSteinbok/ghcpCliDashboard"
            target="_blank"
            rel="noreferrer"
            role="menuitem"
            onClick={() => setOpen(false)}
          >
            About
          </a>
        </div>
      )}
    </div>
  );
}
