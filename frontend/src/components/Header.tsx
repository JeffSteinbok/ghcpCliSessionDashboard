/**
 * Header component — logo, title, waiting badge, credits, theme controls,
 * and last-updated timestamp.
 */

import { useTheme, useVersion } from "../hooks";
import type { Palette } from "../hooks";
import { useAppState } from "../state";
import { PALETTE_OPTIONS } from "../constants";

interface HeaderProps {
  /** Version string from the Python package, e.g. "1.2.3". */
  initialVersion: string;
  /** ISO timestamp string for "last updated" display. */
  lastUpdated: string;
  /** Number of sessions currently in "waiting" state. */
  waitingCount: number;
}

export default function Header({
  initialVersion,
  lastUpdated,
  waitingCount,
}: HeaderProps) {
  const { theme, toggleMode, setPalette } = useTheme();
  const { versionInfo, doUpdate } = useVersion(initialVersion);
  const { serverPid } = useAppState();

  const showUpdateModal = versionInfo.update_available;

  return (
    <div className="header">
      <img
        src="/favicon.png"
        style={{
          width: 32,
          height: 32,
          borderRadius: "50%",
          marginRight: 4,
          verticalAlign: "middle",
        }}
        alt=""
      />
      <h1>Copilot Dashboard</h1>

      {/* Waiting badge — only shown when sessions are waiting for input */}
      {waitingCount > 0 && (
        <span id="waiting-badge" title="Sessions waiting for input">
          ⏳ {waitingCount} waiting
        </span>
      )}

      <div className="header-credits">
        Created by{" "}
        <strong>
          <a
            href="https://github.com/JeffSteinbok"
            target="_blank"
            rel="noreferrer"
          >
            Jeff Steinbok
          </a>
        </strong>
        &nbsp;&bull;&nbsp;
        <span
          id="version-display"
          title={
            showUpdateModal
              ? `v${versionInfo.latest} available — click to update`
              : "Up to date"
          }
          className={showUpdateModal ? "version-update-available" : ""}
          onClick={
            showUpdateModal
              ? () => {
                  if (
                    confirm(
                      `Update from v${versionInfo.current} to v${versionInfo.latest}?`,
                    )
                  ) {
                    doUpdate();
                  }
                }
              : undefined
          }
          style={showUpdateModal ? { cursor: "pointer" } : undefined}
        >
          v{versionInfo.current}
          {showUpdateModal && " ⬆"}
        </span>
        &nbsp;&bull;&nbsp;
        <a
          href="https://github.com/JeffSteinbok/ghcpCliDashboard"
          target="_blank"
          rel="noreferrer"
        >
          What is this?
        </a>
      </div>

      <div className="header-right">
        <div className="theme-controls">
          <button
            className="theme-btn"
            onClick={toggleMode}
            title="Toggle light/dark mode"
          >
            {theme.mode === "dark" ? "🌙 Dark" : "☀️ Light"}
          </button>
          <select
            className="palette-select"
            title="Color palette"
            value={theme.palette}
            onChange={(e) => setPalette(e.target.value as Palette)}
          >
            {PALETTE_OPTIONS.map((p) => (
              <option key={p.value} value={p.value}>
                {p.label}
              </option>
            ))}
          </select>
        </div>
        <div className="header-meta">
          <span className="refresh-dot" />
          <span id="last-updated">{lastUpdated}</span>
        </div>
      </div>

      {/* Server PID — small fixed footer element */}
      {serverPid && (
        <div
          style={{
            position: "fixed",
            bottom: 8,
            right: 12,
            fontSize: 11,
            opacity: 0.4,
            color: "var(--text2)",
            fontFamily: "monospace",
          }}
          title="Dashboard server process ID"
        >
          server PID {serverPid}
        </div>
      )}
    </div>
  );
}
