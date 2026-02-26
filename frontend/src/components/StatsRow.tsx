/**
 * Stats row — summary cards shown above the tab bar when active sessions exist.
 *
 * Displays: Running Now, Conversations, Tool Calls, Sub-agents, Background Tasks.
 */

import type { Session, ProcessMap, BackgroundTask } from "../types";
import BgTaskPopover from "./BgTaskPopover";

interface StatsRowProps {
  active: Session[];
  processes: ProcessMap;
}

export default function StatsRow({ active, processes }: StatsRowProps) {
  if (active.length === 0) return null;

  const turns = active.reduce((a, s) => a + (s.turn_count || 0), 0);
  const toolCalls = active.reduce((a, s) => a + (s.tool_calls || 0), 0);
  const subagents = active.reduce((a, s) => a + (s.subagent_runs || 0), 0);
  const bgTasks = active.reduce(
    (a, s) => a + (processes[s.id]?.bg_tasks || 0),
    0,
  );
  const allBgTasks: BackgroundTask[] = active.flatMap(
    (s) => processes[s.id]?.bg_task_list || [],
  );

  const sub = (
    <div style={{ fontSize: 9, opacity: 0.6, marginTop: 1 }}>
      IN RUNNING SESSIONS
    </div>
  );

  return (
    <div className="stats-row">
      <div className="stat-card">
        <div className="num">{active.length}</div>
        <div className="label">Running Now</div>
      </div>
      <div className="stat-card">
        <div className="num">{turns.toLocaleString()}</div>
        <div className="label">
          Conversations{sub}
        </div>
      </div>
      <div className="stat-card">
        <div className="num">{toolCalls.toLocaleString()}</div>
        <div className="label">
          Tool Calls{sub}
        </div>
      </div>
      <div className="stat-card">
        <div className="num">{subagents.toLocaleString()}</div>
        <div className="label">
          Sub-agents{sub}
        </div>
      </div>
      <div className="stat-card">
        <div className="num">{bgTasks.toLocaleString()}</div>
        <div className="label">
          {bgTasks > 0 ? (
            <BgTaskPopover
              count={bgTasks}
              tasks={allBgTasks}
              label={`Background Tasks`}
              className="badge-bg-stats"
            />
          ) : (
            <>Background Tasks{sub}</>
          )}
        </div>
      </div>
    </div>
  );
}
