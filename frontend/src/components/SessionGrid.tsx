/**
 * Session grid — tile view. Renders sessions as compact cards in a CSS grid.
 *
 * Starred sessions sort first. Clicking a tile opens the detail modal.
 */

import { useState } from "react";
import type { Session, ProcessMap } from "../types";
import { sortStarredFirst } from "../utils";
import { useAppState } from "../state";
import SessionTile from "./SessionTile";
import DetailModal from "./DetailModal";

interface SessionGridProps {
  sessions: Session[];
  processes: ProcessMap;
  isActive: boolean;
}

export default function SessionGrid({ sessions, processes, isActive }: SessionGridProps) {
  const { starredSessions } = useAppState();
  const [modalSession, setModalSession] = useState<{ id: string; title: string } | null>(null);

  if (sessions.length === 0) {
    return (
      <div className="empty">
        {isActive ? "No active sessions detected." : "No previous sessions."}
      </div>
    );
  }

  const sorted = sortStarredFirst(sessions, starredSessions);

  return (
    <>
      <div className="tile-grid">
        {sorted.map((s) => (
          <SessionTile
            key={s.id}
            session={s}
            processInfo={processes[s.id]}
            onOpenDetail={(id, title) => setModalSession({ id, title })}
          />
        ))}
      </div>

      {modalSession && (
        <DetailModal
          sessionId={modalSession.id}
          title={modalSession.title}
          processes={processes}
          sessions={sessions}
          onClose={() => setModalSession(null)}
        />
      )}
    </>
  );
}
