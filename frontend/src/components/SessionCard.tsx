/**
 * Session card — list view. Renders a single session in the expanded list layout.
 *
 * Handles: live dot, title/intent, cwd, recent activity, waiting context,
 * state badges, branch badge, turn/checkpoint counts, MCP servers,
 * restart command row, star toggle, focus/kill buttons.
 */

import type { Session, ProcessInfo } from "../types";
import { COPY_FEEDBACK_MS } from "../constants";import { esc, STATE_LABELS, STATE_BADGE_CLASS, listCardClass } from "../utils";
import { useAppState, useAppDispatch } from "../state";
import { focusSession, killSession } from "../api";
import SessionDetail from "./SessionDetail";
import BgTaskPopover from "./BgTaskPopover";

interface SessionCardProps {
  session: Session;
  processInfo: ProcessInfo | undefined;
}

export default function SessionCard({ session: s, processInfo }: SessionCardProps) {
  const { expandedSessionIds, starredSessions } = useAppState();
  const dispatch = useAppDispatch();

  const isRunning = !!processInfo;
  const state = isRunning ? (processInfo!.state || "unknown") : "";
  const isWaiting = isRunning && state === "waiting";
  const isExpanded = expandedSessionIds.has(s.id);
  const isStarred = starredSessions.has(s.id);

  const cardClass = listCardClass(isRunning, state);

  const handleToggle = () => dispatch({ type: "TOGGLE_EXPAND", sessionId: s.id });
  const handleStar = (e: React.MouseEvent) => {
    e.stopPropagation();
    dispatch({ type: "TOGGLE_STAR", sessionId: s.id });
  };
  const handleCopy = (e: React.MouseEvent, text: string) => {
    e.stopPropagation();
    navigator.clipboard.writeText(text);
  };
  const handleFocus = (e: React.MouseEvent) => {
    e.stopPropagation();
    focusSession(s.id);
  };
  const handleKill = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (processInfo?.pid && confirm(`Kill process PID ${processInfo.pid}?`)) {
      killSession(s.id);
    }
  };

  return (
    <div
      className={`session-card ${cardClass} ${isExpanded ? "expanded" : ""}`}
      data-id={s.id}
    >
      <div style={{ display: "flex", gap: 10 }}>
        <div style={{ flex: 1, minWidth: 0, cursor: "pointer" }} onClick={handleToggle}>
          {/* Timestamp */}
          <div className="session-time" data-tip={`Last updated: ${esc(s.updated_at)}`}>
            started {esc(s.created_ago)}
          </div>

          {/* Title row */}
          <div className="session-top" onClick={handleToggle}>
            {isRunning && (
              <span
                className={`live-dot ${isWaiting ? "waiting" : state === "idle" ? "idle" : ""}`}
                data-tip={isWaiting ? "Waiting for input" : state === "idle" ? "Idle" : "Running"}
              />
            )}
            <div
              className="session-title"
              data-tip={
                isRunning && s.intent
                  ? `Current intent: ${esc(s.intent)}`
                  : `Session: ${esc(s.summary || "")}`
              }
            >
              {isRunning && s.intent ? `🤖 ${s.intent}` : s.summary || "(Untitled session)"}
            </div>
            {isRunning && processInfo!.yolo && (
              <span className="badge badge-yolo" style={{ flexShrink: 0 }}>🔥 YOLO</span>
            )}
          </div>

          {/* CWD */}
          {s.cwd && (
            <div className="cwd-text" data-tip={`Working directory: ${esc(s.cwd)}`}>
              📁 {s.cwd}
            </div>
          )}

          {/* Recent activity */}
          {s.recent_activity && (
            <div className="cwd-text" style={{ color: "var(--accent)" }} data-tip={`Latest checkpoint: ${esc(s.recent_activity)}`}>
              📝 {s.recent_activity}
            </div>
          )}

          {/* Waiting context */}
          {isWaiting && processInfo!.waiting_context && (
            <div className="cwd-text" style={{ color: "var(--yellow)" }} data-tip={`Waiting for: ${esc(processInfo!.waiting_context)}`}>
              ⏳ {processInfo!.waiting_context}
            </div>
          )}

          {/* Badges */}
          <div className="session-meta">
            {isRunning && state && state !== "unknown" && (
              <span className={`badge ${STATE_BADGE_CLASS[state] || "badge-active"}`} data-tip={`State: ${state}`}>
                {STATE_LABELS[state] || ""}
              </span>
            )}
            {isRunning && processInfo!.bg_tasks > 0 && (
              <BgTaskPopover
                count={processInfo!.bg_tasks}
                tasks={processInfo!.bg_task_list || []}
              />
            )}
            {s.branch && (
              <span className="branch-badge" data-tip={`Branch: ${s.repository ? esc(s.repository) + "/" : ""}${esc(s.branch)}`}>
                ⎇ {s.repository ? s.repository + "/" : ""}{s.branch}
              </span>
            )}
            <span className="badge badge-turns" data-tip={`${s.turn_count} conversation turns`}>
              💬 {s.turn_count} turns
            </span>
            {s.checkpoint_count > 0 && (
              <span className="badge badge-cp" data-tip={`${s.checkpoint_count} checkpoint${s.checkpoint_count !== 1 ? "s" : ""}`}>
                🏁 {s.checkpoint_count} checkpoints
              </span>
            )}
            {s.mcp_servers?.map((m) => (
              <span key={m} className="badge badge-mcp" data-tip={`MCP server: ${esc(m)}`}>
                🔌 {m}
              </span>
            ))}
            <span
              className="badge badge-focus star-btn"
              onClick={handleStar}
              data-tip={isStarred ? "Unpin session" : "Pin session"}
            >
              {isStarred ? "⭐" : "☆"}
            </span>
          </div>
        </div>
      </div>

      {/* Restart command row */}
      <div className="restart-row">
        <span className="restart-cmd" data-tip={`Resume command: ${esc(s.restart_cmd)}`}>
          {s.restart_cmd}
        </span>
        <CopyButton text={s.restart_cmd} label="📋 Copy" onCopy={handleCopy} />
        <CopyButton text={s.id} label="🪪" onCopy={handleCopy} />
        {isRunning && (
          <button className="focus-btn" onClick={handleFocus} data-tip="Focus terminal window">
            📺 Focus
          </button>
        )}
        {isRunning && processInfo!.pid > 0 && (
          <span className="list-pid-kill" onClick={(e) => e.stopPropagation()}>
            PID {processInfo!.pid}{" "}
            <span className="tile-kill-x" onClick={handleKill} data-tip={`Kill process PID ${processInfo!.pid}`}>
              ✕
            </span>
          </span>
        )}
      </div>

      {/* Expandable detail panel */}
      <div className="session-detail" id={`detail-${s.id}`}>
        {isExpanded && <SessionDetail sessionId={s.id} />}
      </div>
    </div>
  );
}

// ── Small helper for copy buttons ────────────────────────────────────────────

function CopyButton({
  text,
  label,
  onCopy,
}: {
  text: string;
  label: string;
  onCopy: (e: React.MouseEvent, text: string) => void;
}) {
  const handleClick = (e: React.MouseEvent<HTMLButtonElement>) => {
    onCopy(e, text);
    const btn = e.currentTarget;
    const orig = btn.textContent;
    btn.textContent = "✓";
    setTimeout(() => {
      btn.textContent = orig;
    }, COPY_FEEDBACK_MS);
  };

  return (
    <button className="copy-btn" onClick={handleClick}>
      {label}
    </button>
  );
}
