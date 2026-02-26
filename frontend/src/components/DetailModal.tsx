/**
 * Detail modal — shown when clicking a tile in grid view.
 *
 * Shows session summary info at top, then fetches full detail via API.
 */

import type { Session, ProcessMap } from "../types";
import { esc, STATE_LABELS, STATE_BADGE_CLASS } from "../utils";
import SessionDetail from "./SessionDetail";
import BgTaskPopover from "./BgTaskPopover";

interface DetailModalProps {
  sessionId: string;
  title: string;
  processes: ProcessMap;
  sessions: Session[];
  onClose: () => void;
}

export default function DetailModal({
  sessionId,
  title,
  processes,
  sessions,
  onClose,
}: DetailModalProps) {
  const s = sessions.find((x) => x.id === sessionId);
  const pinfo = s ? processes[s.id] : undefined;
  const isRunning = !!pinfo;
  const state = isRunning ? (pinfo!.state || "unknown") : "";
  const isWaiting = isRunning && state === "waiting";

  const handleOverlayClick = (e: React.MouseEvent) => {
    if (e.target === e.currentTarget) onClose();
  };

  return (
    <div className="detail-modal-overlay open" onClick={handleOverlayClick}>
      <div className="detail-modal">
        <div className="detail-modal-header">
          <h2>{esc(title)}</h2>
          <button className="close-x" onClick={onClose}>✕</button>
        </div>

        {/* Summary section */}
        {s && (
          <div className="detail-section" style={{ marginBottom: 12 }}>
            {isRunning && s.intent && (
              <div style={{ fontWeight: 600, marginBottom: 4 }}>🤖 {esc(s.intent)}</div>
            )}
            {s.branch && (
              <div style={{ marginBottom: 4 }}>
                <span className="branch-badge">
                  ⎇ {s.repository ? esc(s.repository) + "/" : ""}{esc(s.branch)}
                </span>
              </div>
            )}
            {s.recent_activity && (
              <div style={{ color: "var(--accent)", fontSize: 13, marginBottom: 4 }}>
                📝 {esc(s.recent_activity)}
              </div>
            )}
            {isRunning && state && (
              <span className={`badge ${STATE_BADGE_CLASS[state] || "badge-active"}`}>
                {STATE_LABELS[state] || ""}
              </span>
            )}
            {isWaiting && pinfo!.waiting_context && (
              <div style={{ color: "var(--yellow)", fontSize: 13, marginTop: 4 }}>
                ⏳ {esc(pinfo!.waiting_context)}
              </div>
            )}
          </div>
        )}

        {/* Background tasks info */}
        {isRunning && pinfo!.bg_tasks > 0 && (
          <div className="detail-section">
            <h3>⚙️ Background Tasks</h3>
            <BgTaskPopover
              count={pinfo!.bg_tasks}
              tasks={pinfo!.bg_task_list || []}
              label={`${pinfo!.bg_tasks} background task${pinfo!.bg_tasks > 1 ? "s" : ""} currently running — hover for details`}
            />
          </div>
        )}

        {/* Full detail (checkpoints, turns, refs, etc.) */}
        <SessionDetail sessionId={sessionId} />
      </div>
    </div>
  );
}
