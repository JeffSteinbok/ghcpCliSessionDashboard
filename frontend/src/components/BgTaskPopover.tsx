/**
 * BgTaskPopover — hover popover showing the list of running background tasks.
 *
 * Wraps the bg tasks badge and shows a dropdown popover on mouseenter
 * with individual task names and descriptions.
 */

import { useState, useRef, useCallback } from "react";
import type { BackgroundTask } from "../types";
import { esc } from "../utils";

interface BgTaskPopoverProps {
  count: number;
  tasks: BackgroundTask[];
  /** Optional label override — defaults to "⚙️ {count} bg task(s)" */
  label?: string;
  /** Extra className for the badge */
  className?: string;
}

export default function BgTaskPopover({ count, tasks, label, className = "" }: BgTaskPopoverProps) {
  const [visible, setVisible] = useState(false);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const show = useCallback(() => {
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => setVisible(true), 300);
  }, []);

  const hide = useCallback(() => {
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => setVisible(false), 150);
  }, []);

  const badgeLabel = label ?? `⚙️ ${count} bg task${count > 1 ? "s" : ""}`;

  return (
    <span
      className="bg-task-popover-wrap"
      onMouseEnter={show}
      onMouseLeave={hide}
    >
      <span className={`badge badge-bg ${className}`}>
        {badgeLabel}
      </span>
      {visible && (
        <div className="bg-task-popover" onMouseEnter={show} onMouseLeave={hide}>
          <div className="pop-title">⚙️ Background Tasks ({count})</div>
          {tasks.length > 0 ? (
            <ul className="bg-task-list">
              {tasks.map((t, i) => (
                <li key={i} className="bg-task-item">
                  <span className="bg-task-name">{esc(t.agent_name)}</span>
                  {t.description && (
                    <span className="bg-task-desc">{esc(t.description.substring(0, 120))}</span>
                  )}
                </li>
              ))}
            </ul>
          ) : (
            <div className="bg-task-empty">
              {count} background task{count > 1 ? "s" : ""} running
            </div>
          )}
        </div>
      )}
    </span>
  );
}
