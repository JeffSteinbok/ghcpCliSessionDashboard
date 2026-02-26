import { useEffect, useRef } from "react";
import { fetchSessions, fetchProcesses } from "../api";
import { PROCESS_POLL_MS, SESSION_POLL_MS } from "../constants";
import { useAppState, useAppDispatch } from "../state";
import type { ProcessMap } from "../types";

/**
 * Polls /api/sessions every 30s and /api/processes every 5s.
 */
export function useSessions() {
  const dispatch = useAppDispatch();
  const { notificationsEnabled, sessions, processes } = useAppState();
  const prevProcesses = useRef<ProcessMap>({});
  const sessionsRef = useRef(sessions);
  const notifRef = useRef(notificationsEnabled);
  sessionsRef.current = sessions;
  notifRef.current = notificationsEnabled;

  // Full session + process fetch
  const fetchAll = async () => {
    try {
      const [sess, procs] = await Promise.all([
        fetchSessions(),
        fetchProcesses(),
      ]);
      dispatch({ type: "SET_SESSIONS", sessions: sess });
      checkTransitions(prevProcesses.current, procs);
      prevProcesses.current = procs;
      dispatch({ type: "SET_PROCESSES", processes: procs });
      dispatch({ type: "RECORD_FETCH_SUCCESS" });
    } catch {
      dispatch({ type: "RECORD_FETCH_FAILURE" });
    }
  };

  // Process-only fetch (fast poll)
  const fetchProcs = async () => {
    try {
      const procs = await fetchProcesses();
      checkTransitions(prevProcesses.current, procs);
      prevProcesses.current = procs;
      dispatch({ type: "SET_PROCESSES", processes: procs });
      dispatch({ type: "RECORD_FETCH_SUCCESS" });
    } catch {
      dispatch({ type: "RECORD_FETCH_FAILURE" });
    }
  };

  // Desktop notification on state transition
  const checkTransitions = (oldP: ProcessMap, newP: ProcessMap) => {
    if (!notifRef.current) return;
    for (const [sid, info] of Object.entries(newP)) {
      const oldState = oldP[sid]?.state ?? null;
      if (!oldState) continue;
      if (
        info.state !== oldState &&
        (info.state === "waiting" || info.state === "idle")
      ) {
        const session = sessionsRef.current.find((s) => s.id === sid);
        const title = session
          ? session.intent || session.summary || "Copilot Session"
          : "Copilot Session";
        const body =
          info.waiting_context ||
          (info.state === "waiting"
            ? "Session is waiting for your input"
            : "Session is done and ready for next task");
        new Notification(title, { body, tag: "copilot-" + sid });
      }
    }
  };

  useEffect(() => {
    fetchAll();
    const activeTimer = setInterval(fetchProcs, PROCESS_POLL_MS);
    const fullTimer = setInterval(fetchAll, SESSION_POLL_MS);
    return () => {
      clearInterval(activeTimer);
      clearInterval(fullTimer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return { processes, sessions };
}
