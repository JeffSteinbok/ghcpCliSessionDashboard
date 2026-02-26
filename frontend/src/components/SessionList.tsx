/**
 * Session list view — grouped sessions in a vertical card layout.
 *
 * Groups sessions by project, sorts groups by size, starred first within each.
 */

import type { Session, ProcessMap } from "../types";
import { groupSessions, sortStarredFirst } from "../utils";
import { useAppState, useAppDispatch } from "../state";
import SessionCard from "./SessionCard";

interface SessionListProps {
  sessions: Session[];
  processes: ProcessMap;
  isActive: boolean;
  panelId: string;
}

export default function SessionList({ sessions, processes, isActive, panelId }: SessionListProps) {
  const { collapsedGroups, starredSessions } = useAppState();
  const dispatch = useAppDispatch();

  if (sessions.length === 0) {
    return (
      <div className="empty">
        {isActive ? "No active sessions detected." : "No previous sessions."}
      </div>
    );
  }

  const groups = groupSessions(sessions);

  return (
    <>
      {groups.map(([groupName, items]) => {
        const gid = `${panelId}-${groupName}`.replace(/[^a-zA-Z0-9]/g, "_");
        const isCollapsed = collapsedGroups.has(gid);
        const sorted = sortStarredFirst(items, starredSessions);

        return (
          <div key={gid} className="group">
            <div
              className={`group-header ${isCollapsed ? "collapsed" : ""}`}
              onClick={() => dispatch({ type: "TOGGLE_GROUP", groupId: gid })}
            >
              <span className="arrow">▼</span>
              {groupName}
              <span className="group-count">({items.length})</span>
            </div>
            <div className="group-body">
              {sorted.map((s) => (
                <SessionCard
                  key={s.id}
                  session={s}
                  processInfo={processes[s.id]}
                />
              ))}
            </div>
          </div>
        );
      })}
    </>
  );
}
