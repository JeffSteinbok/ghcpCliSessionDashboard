/**
 * Timeline tab — Gantt-style horizontal bars showing session activity
 * over the last 5 days.
 *
 * Renders horizontal bars positioned proportionally within the 5-day window.
 */

import { useMemo } from "react";
import { PREVIOUS_SESSION_WINDOW_MS } from "../constants";
import type { Session, ProcessMap } from "../types";
import { esc } from "../utils";

interface TimelineProps {
  sessions: Session[];
  processes: ProcessMap;
  /** Current timestamp — passed from parent to keep render pure. */
  now: number;
  onOpenDetail: (id: string, title: string) => void;
}

/** State → bar color mapping. */
const STATE_COLORS: Record<string, string> = {
  working: "var(--green)",
  thinking: "var(--green)",
  waiting: "var(--yellow)",
  idle: "var(--accent)",
};

interface BarData {
  session: Session;
  leftPct: number;
  widthPct: number;
  color: string;
  label: string;
}

export default function Timeline({ sessions, processes, now, onOpenDetail }: TimelineProps) {
  // All time-dependent computation in useMemo
  const timeline = useMemo(() => {
    const fiveDaysAgo = now - PREVIOUS_SESSION_WINDOW_MS;

    const filtered = sessions
      .filter(
        (s) =>
          s.created_at &&
          s.updated_at &&
          new Date(s.updated_at).getTime() >= fiveDaysAgo,
      )
      .sort(
        (a, b) =>
          new Date(a.created_at).getTime() - new Date(b.created_at).getTime(),
      );

    if (filtered.length === 0) return null;

    const minTime = new Date(filtered[0].created_at).getTime();
    const maxTime = Math.max(
      now,
      ...filtered.map((s) => new Date(s.updated_at).getTime()),
    );
    const totalMs = maxTime - minTime || 1;

    // Time labels (5 evenly-spaced markers)
    const labelCount = 5;
    const labels = Array.from({ length: labelCount + 1 }, (_, i) => {
      const t = new Date(minTime + (totalMs * i) / labelCount);
      return `${t.toLocaleDateString()} ${t.toLocaleTimeString([], {
        hour: "2-digit",
        minute: "2-digit",
      })}`;
    });

    // Pre-compute bar positions
    const bars: BarData[] = filtered.map((s) => {
      const start = new Date(s.created_at).getTime();
      const end = processes[s.id] ? now : new Date(s.updated_at).getTime();
      const pinfo = processes[s.id];
      const state = pinfo?.state || (processes[s.id] ? "working" : "previous");
      return {
        session: s,
        leftPct: ((start - minTime) / totalMs) * 100,
        widthPct: Math.max(0.3, ((end - start) / totalMs) * 100),
        color: STATE_COLORS[state] || "var(--border)",
        label: (s.summary || "(Untitled)").substring(0, 30),
      };
    });

    return { labels, bars, labelCount };
  }, [sessions, processes, now]);

  if (!timeline) {
    return <div className="empty">No sessions with timestamps.</div>;
  }

  const { labels, bars, labelCount } = timeline;

  return (
    <div style={{ padding: "8px 0" }}>
      {/* Header time labels */}
      <div
        style={{
          display: "flex",
          marginLeft: 220,
          marginBottom: 4,
          fontSize: 11,
          color: "var(--text2)",
        }}
      >
        {labels.map((label, i) => (
          <div
            key={i}
            style={{
              flex: 1,
              textAlign: i === labelCount ? "right" : undefined,
            }}
          >
            {label}
          </div>
        ))}
      </div>

      {/* Session bars */}
      {bars.map(({ session: s, leftPct, widthPct, color, label }) => (
        <div
          key={s.id}
          style={{
            display: "flex",
            alignItems: "center",
            marginBottom: 4,
            gap: 8,
          }}
        >
          <div
            style={{
              width: 212,
              minWidth: 212,
              fontSize: 12,
              color: "var(--text2)",
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
              textAlign: "right",
              paddingRight: 8,
            }}
            title={s.summary || ""}
          >
            {esc(label)}
          </div>

          <div
            style={{
              flex: 1,
              position: "relative",
              height: 20,
              background: "var(--surface2)",
              borderRadius: 4,
              cursor: "pointer",
            }}
            onClick={() => onOpenDetail(s.id, s.summary || "(Untitled)")}
          >
            <div
              style={{
                position: "absolute",
                left: `${leftPct.toFixed(2)}%`,
                width: `${widthPct.toFixed(2)}%`,
                height: "100%",
                background: color,
                borderRadius: 4,
                minWidth: 4,
                opacity: 0.85,
              }}
              title={`${esc(s.summary || "")} — ${esc(s.created_ago)}`}
            />
          </div>
        </div>
      ))}
    </div>
  );
}
