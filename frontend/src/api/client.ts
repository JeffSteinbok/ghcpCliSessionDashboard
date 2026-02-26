/**
 * Typed API client for the Copilot Dashboard backend.
 *
 * Each function maps 1:1 to a FastAPI route in dashboard_api.py.
 * All responses are typed to match the Pydantic models (src/schemas.py).
 */

import type {
  Session,
  SessionDetail,
  ProcessMap,
  FileFrequency,
  VersionInfo,
  ServerInfo,
} from "../types";

/** Generic GET helper — throws on non-2xx responses. */
async function get<T>(url: string): Promise<T> {
  const resp = await fetch(url);
  if (!resp.ok) throw new Error(`${resp.status} ${resp.statusText}`);
  return resp.json() as Promise<T>;
}

/** Generic POST helper — throws on non-2xx responses. */
async function post<T>(url: string): Promise<T> {
  const resp = await fetch(url, { method: "POST" });
  if (!resp.ok) throw new Error(`${resp.status} ${resp.statusText}`);
  return resp.json() as Promise<T>;
}

// ── Session data ─────────────────────────────────────────────────────────────

/** Fetch all sessions with enriched metadata (groups, restart cmds, etc.). */
export function fetchSessions(): Promise<Session[]> {
  return get<Session[]>("/api/sessions");
}

/** Fetch detailed info for a single session (checkpoints, turns, refs). */
export function fetchSessionDetail(id: string): Promise<SessionDetail> {
  return get<SessionDetail>(`/api/session/${id}`);
}

/** Fetch files most frequently edited across recent sessions. */
export function fetchFiles(): Promise<FileFrequency[]> {
  return get<FileFrequency[]>("/api/files");
}

// ── Process tracking ─────────────────────────────────────────────────────────

/** Fetch currently-running Copilot processes, keyed by session ID. */
export function fetchProcesses(): Promise<ProcessMap> {
  return get<ProcessMap>("/api/processes");
}

/** Bring a session's terminal window to the foreground (Windows only). */
export function focusSession(
  id: string,
): Promise<{ success: boolean; message: string }> {
  return post(`/api/focus/${id}`);
}

/** Kill a running session's process. */
export function killSession(
  id: string,
): Promise<{ success: boolean; message: string }> {
  return post(`/api/kill/${encodeURIComponent(id)}`);
}

// ── Server management ────────────────────────────────────────────────────────

/** Check for a newer version on PyPI. */
export function fetchVersion(): Promise<VersionInfo> {
  return get<VersionInfo>("/api/version");
}

/** Get the dashboard server's PID and port. */
export function fetchServerInfo(): Promise<ServerInfo> {
  return get<ServerInfo>("/api/server-info");
}

/**
 * Trigger a self-update via pip. The server dies mid-response while
 * upgrading itself, so fetch errors are expected and swallowed.
 */
export async function triggerUpdate(): Promise<void> {
  try {
    await fetch("/api/update", { method: "POST" });
  } catch {
    // Server dies mid-response during self-update — this is expected
  }
}
