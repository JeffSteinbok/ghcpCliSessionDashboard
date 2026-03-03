/**
 * Popover prompting the user to enable autostart at login.
 * Shown once on mount when autostart is supported but not enabled.
 */

import { useAutostart } from "../hooks";

export default function AutostartPopover() {
  const { showPrompt, toggling, enable, dismiss } = useAutostart();

  if (!showPrompt) return null;

  return (
    <div
      style={{
        position: "fixed",
        bottom: 48,
        right: 16,
        zIndex: 9999,
        background: "var(--bg2, #2a2a3d)",
        color: "var(--text, #e0e0e0)",
        border: "1px solid var(--border, #444)",
        borderRadius: 10,
        padding: "16px 20px",
        maxWidth: 340,
        boxShadow: "0 8px 24px rgba(0,0,0,0.35)",
        fontFamily: "inherit",
        fontSize: 14,
        lineHeight: 1.5,
      }}
    >
      <div style={{ fontWeight: 600, marginBottom: 6, fontSize: 15 }}>
        🚀 Start on login?
      </div>
      <div style={{ marginBottom: 12, opacity: 0.85 }}>
        Would you like the dashboard to start automatically when you log in?
      </div>
      <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
        <button
          onClick={dismiss}
          style={{
            background: "transparent",
            border: "1px solid var(--border, #555)",
            color: "var(--text, #ccc)",
            borderRadius: 6,
            padding: "5px 14px",
            cursor: "pointer",
            fontSize: 13,
          }}
        >
          No thanks
        </button>
        <button
          onClick={enable}
          disabled={toggling}
          style={{
            background: "var(--accent, #58a6ff)",
            border: "none",
            color: "#fff",
            borderRadius: 6,
            padding: "5px 14px",
            cursor: toggling ? "wait" : "pointer",
            fontSize: 13,
            fontWeight: 600,
          }}
        >
          {toggling ? "Enabling…" : "Enable"}
        </button>
      </div>
    </div>
  );
}
