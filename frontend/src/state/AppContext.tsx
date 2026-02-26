/**
 * Global application state management using React Context + useReducer.
 *
 * Centralises all application state (sessions, processes, current tab,
 * expanded IDs, etc.) into a single typed state tree managed by a reducer.
 * The reducer is a pure function — easy to test without rendering components.
 *
 * Usage:
 *   const state = useAppState();
 *   const dispatch = useAppDispatch();
 *   dispatch({ type: "SET_TAB", tab: "timeline" });
 */

import {
  createContext,
  useContext,
  useReducer,
  type Dispatch,
  type ReactNode,
} from "react";
import {
  DISCONNECT_THRESHOLD,
  STORAGE_KEY_STARRED,
  STORAGE_KEY_VIEW,
} from "../constants";
import type { Session, ProcessMap } from "../types";

// ── State shape ──────────────────────────────────────────────────────────────

export type Tab = "active" | "previous" | "timeline" | "files";
export type View = "tile" | "list";

export interface AppState {
  sessions: Session[];
  processes: ProcessMap;
  currentTab: Tab;
  currentView: View;
  searchFilter: string;
  expandedSessionIds: Set<string>;
  collapsedGroups: Set<string>;
  starredSessions: Set<string>;
  loadedDetails: Record<string, string>;
  notificationsEnabled: boolean;
  consecutiveFailures: number;
  serverPid: number | null;
}

export function initialState(): AppState {
  return {
    sessions: [],
    processes: {},
    currentTab: "active",
    currentView:
      (localStorage.getItem(STORAGE_KEY_VIEW) as View) || "tile",
    searchFilter: "",
    expandedSessionIds: new Set(),
    collapsedGroups: new Set(),
    starredSessions: new Set(
      JSON.parse(localStorage.getItem(STORAGE_KEY_STARRED) || "[]") as string[],
    ),
    loadedDetails: {},
    notificationsEnabled:
      typeof Notification !== "undefined" &&
      Notification.permission === "granted",
    consecutiveFailures: 0,
    serverPid: null,
  };
}

// ── Actions ──────────────────────────────────────────────────────────────────

export type Action =
  | { type: "SET_SESSIONS"; sessions: Session[] }
  | { type: "SET_PROCESSES"; processes: ProcessMap }
  | { type: "SET_TAB"; tab: Tab }
  | { type: "SET_VIEW"; view: View }
  | { type: "SET_SEARCH"; filter: string }
  | { type: "TOGGLE_EXPAND"; sessionId: string }
  | { type: "TOGGLE_GROUP"; groupId: string }
  | { type: "TOGGLE_STAR"; sessionId: string }
  | { type: "CACHE_DETAIL"; sessionId: string; html: string }
  | { type: "SET_NOTIFICATIONS"; enabled: boolean }
  | { type: "RECORD_FETCH_SUCCESS" }
  | { type: "RECORD_FETCH_FAILURE" }
  | { type: "SET_SERVER_PID"; pid: number };

// ── Reducer ──────────────────────────────────────────────────────────────────

export function appReducer(state: AppState, action: Action): AppState {
  switch (action.type) {
    case "SET_SESSIONS":
      return { ...state, sessions: action.sessions };

    case "SET_PROCESSES":
      return { ...state, processes: action.processes };

    case "SET_TAB":
      return { ...state, currentTab: action.tab };

    case "SET_VIEW":
      localStorage.setItem(STORAGE_KEY_VIEW, action.view);
      return { ...state, currentView: action.view };

    case "SET_SEARCH":
      return { ...state, searchFilter: action.filter };

    case "TOGGLE_EXPAND": {
      const next = new Set(state.expandedSessionIds);
      if (next.has(action.sessionId)) {
        next.delete(action.sessionId);
      } else {
        next.clear();
        next.add(action.sessionId);
      }
      return { ...state, expandedSessionIds: next };
    }

    case "TOGGLE_GROUP": {
      const next = new Set(state.collapsedGroups);
      if (next.has(action.groupId)) next.delete(action.groupId);
      else next.add(action.groupId);
      return { ...state, collapsedGroups: next };
    }

    case "TOGGLE_STAR": {
      const next = new Set(state.starredSessions);
      if (next.has(action.sessionId)) next.delete(action.sessionId);
      else next.add(action.sessionId);
      localStorage.setItem(STORAGE_KEY_STARRED, JSON.stringify([...next]));
      return { ...state, starredSessions: next };
    }

    case "CACHE_DETAIL":
      return {
        ...state,
        loadedDetails: {
          ...state.loadedDetails,
          [action.sessionId]: action.html,
        },
      };

    case "SET_NOTIFICATIONS":
      return { ...state, notificationsEnabled: action.enabled };

    case "RECORD_FETCH_SUCCESS":
      return { ...state, consecutiveFailures: 0 };

    case "RECORD_FETCH_FAILURE":
      return {
        ...state,
        consecutiveFailures: state.consecutiveFailures + 1,
      };

    case "SET_SERVER_PID":
      return { ...state, serverPid: action.pid };

    default:
      return state;
  }
}

// ── Selectors ────────────────────────────────────────────────────────────────

export function isDisconnected(state: AppState): boolean {
  return state.consecutiveFailures >= DISCONNECT_THRESHOLD;
}

// ── Context ──────────────────────────────────────────────────────────────────

const AppStateContext = createContext<AppState | null>(null);
const AppDispatchContext = createContext<Dispatch<Action> | null>(null);

export function AppProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(appReducer, undefined, initialState);
  return (
    <AppStateContext.Provider value={state}>
      <AppDispatchContext.Provider value={dispatch}>
        {children}
      </AppDispatchContext.Provider>
    </AppStateContext.Provider>
  );
}

export function useAppState(): AppState {
  const ctx = useContext(AppStateContext);
  if (!ctx) throw new Error("useAppState must be used within AppProvider");
  return ctx;
}

export function useAppDispatch(): Dispatch<Action> {
  const ctx = useContext(AppDispatchContext);
  if (!ctx) throw new Error("useAppDispatch must be used within AppProvider");
  return ctx;
}
