/**
 * Session tile — compact card for the grid/tile view.
 */

import type { Session, ProcessInfo } from "../types";
import { COPY_FEEDBACK_MS } from "../constants";
import { esc, STATE_LABELS, STATE_BADGE_CLASS, TILE_STATE_CLASS } from "../utils";
import { useAppState, useAppDispatch } from "../state";
import { focusSession, killSession } from "../api";

interface SessionTileProps {
  session: Session;
  processInfo: ProcessInfo | undefined;
  onOpenDetail: (id: string, title: string) => void;
}

export default function SessionTile({ session: s, processInfo, onOpenDetail }: SessionTileProps) {
  const { starredSessions } = useAppState();
  const dispatch = useAppDispatch();

  const isRunning = !!processInfo;
  const state = isRunning ? (processInfo!.state || "unknown") : "";
  const isWaiting = isRunning && state === "waiting";
  const isStarred = starredSessions.has(s.id);
  const tileClass = isRunning ? (TILE_STATE_CLASS[state] || "") : "";

  const handleClick = () => onOpenDetail(s.id, s.summary || "(Untitled)");
  const stop = (e: React.MouseEvent) => e.stopPropagation();

  const handleCopy = (e: React.MouseEvent) => {
    stop(e);
    navigator.clipboard.writeText(s.restart_cmd);
    const btn = e.currentTarget;
    const orig = btn.textContent;
    btn.textContent = "✓";
    setTimeout(() => { btn.textContent = orig; }, COPY_FEEDBACK_MS);
  };

  const handleCopyId = (e: React.MouseEvent) => {
    stop(e);
    navigator.clipboard.writeText(s.id);
    const btn = e.currentTarget;
    btn.textContent = "✓";
    setTimeout(() => { btn.textContent = "🪪"; }, COPY_FEEDBACK_MS);
  };

  return (
    <div className={`tile-card ${tileClass}`} onClick={handleClick}>
      <div className="tile-subtitle" style={{ fontSize: 11, opacity: 0.7 }}>
        started {esc(s.created_ago)}
      </div>

      {/* Title row */}
      <div className="tile-top">
        {isRunning && (
          <span
            className={`live-dot ${isWaiting ? "waiting" : state === "idle" ? "idle" : ""}`}
            style={{ flexShrink: 0 }}
          />
        )}
        <div
          className="tile-title"
          data-tip={
            isRunning && s.intent
              ? `Intent: ${esc(s.intent)}`
              : `Session: ${esc(s.summary || "(Untitled session)")}`
          }
        >
          {isRunning && s.intent ? `🤖 ${s.intent}` : s.summary || "(Untitled session)"}
        </div>
        {isRunning && processInfo!.yolo && (
          <span className="badge badge-yolo" style={{ flexShrink: 0 }}>🔥</span>
        )}
      </div>

      {/* Branch */}
      {s.branch && (
        <div className="tile-subtitle">
          <span
            className="branch-badge"
            data-tip={`Repository/Branch: ${s.repository ? esc(s.repository) + "/" : ""}${esc(s.branch)}`}
          >
            ⎇ {s.repository ? s.repository + "/" : ""}{s.branch}
          </span>
        </div>
      )}

      {/* Recent activity */}
      {s.recent_activity && (
        <div className="tile-subtitle" style={{ color: "var(--accent)" }} data-tip={`Latest checkpoint: ${esc(s.recent_activity)}`}>
          {s.recent_activity}
        </div>
      )}

      {/* Waiting context */}
      {isWaiting && processInfo!.waiting_context && (
        <div className="tile-subtitle" style={{ color: "var(--yellow)" }} data-tip={`Waiting for: ${esc(processInfo!.waiting_context)}`}>
          {processInfo!.waiting_context.substring(0, 80)}
          {processInfo!.waiting_context.length > 80 ? "..." : ""}
        </div>
      )}

      {/* Badge row */}
      <div className="tile-meta">
        {isRunning && state && state !== "unknown" && (
          <span className={`badge ${STATE_BADGE_CLASS[state] || "badge-active"}`}>
            {STATE_LABELS[state] || state}
          </span>
        )}
        {isRunning && processInfo!.bg_tasks > 0 && (
          <span className="badge badge-bg">⚙️ {processInfo!.bg_tasks} bg</span>
        )}
        <span className="badge badge-turns">💬 {s.turn_count}</span>
        {s.checkpoint_count > 0 && (
          <span className="badge badge-cp" data-tip={`${s.checkpoint_count} checkpoint${s.checkpoint_count !== 1 ? "s" : ""}`}>
            🏁 {s.checkpoint_count}
          </span>
        )}
        {s.mcp_servers?.map((m) => (
          <span key={m} className="badge badge-mcp">🔌 {m}</span>
        ))}
        {isRunning && (
          <span className="badge badge-focus" onClick={(e) => { stop(e); focusSession(s.id); }} data-tip="Focus terminal window">
            👁️
          </span>
        )}
        <span className="badge badge-focus" onClick={handleCopy} data-tip="Copy resume command">📋</span>
        <span className="badge badge-focus" onClick={handleCopyId} data-tip="Copy session ID">🪪</span>
        <span
          className="badge badge-focus star-btn"
          onClick={(e) => { stop(e); dispatch({ type: "TOGGLE_STAR", sessionId: s.id }); }}
          data-tip={isStarred ? "Unpin session" : "Pin session"}
        >
          {isStarred ? "⭐" : "☆"}
        </span>
      </div>

      {/* PID + kill button */}
      {isRunning && processInfo!.pid > 0 && (
        <div className="tile-pid-kill" onClick={stop}>
          PID {processInfo!.pid}{" "}
          <span
            className="tile-kill-x"
            onClick={() => {
              if (confirm(`Kill process PID ${processInfo!.pid}?`)) {
                killSession(s.id);
              }
            }}
            data-tip="Kill process"
          >
            ✕
          </span>
        </div>
      )}
    </div>
  );
}
