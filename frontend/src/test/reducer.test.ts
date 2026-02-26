/**
 * Tests for the AppContext reducer — pure function, no React rendering needed.
 */

import { describe, it, expect, beforeEach, vi } from "vitest";
import { appReducer, initialState, isDisconnected } from "../state/AppContext";
import type { AppState } from "../state/AppContext";
import {
  STORAGE_KEY_STARRED,
  STORAGE_KEY_VIEW,
} from "../constants";

// Mock localStorage for initialState
const store: Record<string, string> = {};
vi.stubGlobal("localStorage", {
  getItem: (key: string) => store[key] ?? null,
  setItem: (key: string, val: string) => { store[key] = val; },
  removeItem: (key: string) => { delete store[key]; },
});

let state: AppState;

beforeEach(() => {
  Object.keys(store).forEach((k) => delete store[k]);
  state = initialState();
});

describe("initialState()", () => {
  it("defaults to tile view and dark mode prefs", () => {
    expect(state.currentView).toBe("tile");
    expect(state.currentTab).toBe("active");
    expect(state.sessions).toEqual([]);
    expect(state.consecutiveFailures).toBe(0);
  });

  it("reads starred sessions from localStorage", () => {
    store[STORAGE_KEY_STARRED] = '["abc","def"]';
    const s = initialState();
    expect(s.starredSessions.has("abc")).toBe(true);
    expect(s.starredSessions.has("def")).toBe(true);
  });

  it("reads view preference from localStorage", () => {
    store[STORAGE_KEY_VIEW] = "list";
    const s = initialState();
    expect(s.currentView).toBe("list");
  });
});

describe("appReducer", () => {
  it("SET_TAB changes current tab", () => {
    const next = appReducer(state, { type: "SET_TAB", tab: "timeline" });
    expect(next.currentTab).toBe("timeline");
  });

  it("SET_VIEW changes view", () => {
    const next = appReducer(state, { type: "SET_VIEW", view: "list" });
    expect(next.currentView).toBe("list");
  });

  it("SET_SEARCH updates filter", () => {
    const next = appReducer(state, { type: "SET_SEARCH", filter: "auth" });
    expect(next.searchFilter).toBe("auth");
  });

  it("TOGGLE_EXPAND adds session ID, clears previous", () => {
    let next = appReducer(state, { type: "TOGGLE_EXPAND", sessionId: "a" });
    expect(next.expandedSessionIds.has("a")).toBe(true);
    next = appReducer(next, { type: "TOGGLE_EXPAND", sessionId: "b" });
    expect(next.expandedSessionIds.has("a")).toBe(false);
    expect(next.expandedSessionIds.has("b")).toBe(true);
  });

  it("TOGGLE_EXPAND collapses when same ID toggled", () => {
    let next = appReducer(state, { type: "TOGGLE_EXPAND", sessionId: "a" });
    next = appReducer(next, { type: "TOGGLE_EXPAND", sessionId: "a" });
    expect(next.expandedSessionIds.size).toBe(0);
  });

  it("TOGGLE_GROUP toggles group collapsed state", () => {
    let next = appReducer(state, { type: "TOGGLE_GROUP", groupId: "g1" });
    expect(next.collapsedGroups.has("g1")).toBe(true);
    next = appReducer(next, { type: "TOGGLE_GROUP", groupId: "g1" });
    expect(next.collapsedGroups.has("g1")).toBe(false);
  });

  it("TOGGLE_STAR toggles starred sessions", () => {
    let next = appReducer(state, { type: "TOGGLE_STAR", sessionId: "s1" });
    expect(next.starredSessions.has("s1")).toBe(true);

    next = appReducer(next, { type: "TOGGLE_STAR", sessionId: "s1" });
    expect(next.starredSessions.has("s1")).toBe(false);
  });

  it("RECORD_FETCH_SUCCESS resets failure counter", () => {
    state = { ...state, consecutiveFailures: 5 };
    const next = appReducer(state, { type: "RECORD_FETCH_SUCCESS" });
    expect(next.consecutiveFailures).toBe(0);
  });

  it("RECORD_FETCH_FAILURE increments failure counter", () => {
    const next = appReducer(state, { type: "RECORD_FETCH_FAILURE" });
    expect(next.consecutiveFailures).toBe(1);
  });

  it("SET_SERVER_PID stores pid", () => {
    const next = appReducer(state, { type: "SET_SERVER_PID", pid: 9999 });
    expect(next.serverPid).toBe(9999);
  });
});

describe("isDisconnected()", () => {
  it("returns false when failures < 2", () => {
    expect(isDisconnected({ ...state, consecutiveFailures: 1 })).toBe(false);
  });

  it("returns true when failures >= 2", () => {
    expect(isDisconnected({ ...state, consecutiveFailures: 2 })).toBe(true);
    expect(isDisconnected({ ...state, consecutiveFailures: 5 })).toBe(true);
  });
});
