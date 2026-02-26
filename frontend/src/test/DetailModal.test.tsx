/**
 * Tests for DetailModal and FilesTab components.
 */

import { render, screen, fireEvent, act } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import type { Session, ProcessMap } from "../types";
import DetailModal from "../components/DetailModal";
import FilesTab from "../components/FilesTab";

// ── Factories ────────────────────────────────────────────────────────────────

function makeSession(overrides: Partial<Session> = {}): Session {
  return {
    id: "test-id",
    cwd: null,
    repository: null,
    branch: null,
    summary: "Test session",
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T01:00:00Z",
    created_ago: "1 hour ago",
    time_ago: "1 hour ago",
    turn_count: 5,
    file_count: 3,
    checkpoint_count: 1,
    is_running: false,
    state: null,
    waiting_context: "",
    bg_tasks: 0,
    group: "General",
    recent_activity: null,
    restart_cmd: "copilot",
    mcp_servers: [],
    tool_calls: 10,
    subagent_runs: 2,
    intent: "",
    ...overrides,
  };
}

// ── Mock fetch ───────────────────────────────────────────────────────────────

const mockFetch = vi.fn();
vi.stubGlobal("fetch", mockFetch);

const store: Record<string, string> = {};
vi.stubGlobal("localStorage", {
  getItem: (key: string) => store[key] ?? null,
  setItem: (key: string, val: string) => { store[key] = val; },
  removeItem: (key: string) => { delete store[key]; },
});

beforeEach(() => {
  mockFetch.mockReset();
  Object.keys(store).forEach((k) => delete store[k]);
});

// ── DetailModal ──────────────────────────────────────────────────────────────

describe("DetailModal", () => {
  const defaultProps = {
    sessionId: "test-id",
    title: "My Session",
    processes: {} as ProcessMap,
    sessions: [makeSession()],
    onClose: vi.fn(),
  };

  beforeEach(() => {
    defaultProps.onClose.mockClear();
    mockFetch.mockResolvedValue({
      ok: true,
      status: 200,
      json: () =>
        Promise.resolve({
          checkpoints: [],
          refs: [],
          turns: [],
          recent_output: [],
          tool_counts: [],
          files: [],
        }),
    });
  });

  it("renders the modal title", () => {
    render(<DetailModal {...defaultProps} />);
    expect(screen.getByText("My Session")).toBeInTheDocument();
  });

  it("renders the overlay element", () => {
    const { container } = render(<DetailModal {...defaultProps} />);
    expect(container.querySelector(".detail-modal-overlay")).not.toBeNull();
  });

  it("renders close button", () => {
    render(<DetailModal {...defaultProps} />);
    expect(screen.getByText("✕")).toBeInTheDocument();
  });

  it("calls onClose when close button clicked", () => {
    render(<DetailModal {...defaultProps} />);
    fireEvent.click(screen.getByText("✕"));
    expect(defaultProps.onClose).toHaveBeenCalledTimes(1);
  });

  it("calls onClose when overlay is clicked", () => {
    const { container } = render(<DetailModal {...defaultProps} />);
    const overlay = container.querySelector(".detail-modal-overlay")!;
    fireEvent.click(overlay);
    expect(defaultProps.onClose).toHaveBeenCalledTimes(1);
  });

  it("does not call onClose when modal content is clicked", () => {
    const { container } = render(<DetailModal {...defaultProps} />);
    const modal = container.querySelector(".detail-modal")!;
    fireEvent.click(modal);
    expect(defaultProps.onClose).not.toHaveBeenCalled();
  });

  it("shows branch badge when session has a branch", () => {
    const sessions = [makeSession({ branch: "feature", repository: "org/repo" })];
    render(<DetailModal {...defaultProps} sessions={sessions} />);
    expect(screen.getByText(/org\/repo\/feature/)).toBeInTheDocument();
  });

  it("shows recent activity when present", () => {
    const sessions = [makeSession({ recent_activity: "Fixed a bug" })];
    render(<DetailModal {...defaultProps} sessions={sessions} />);
    expect(screen.getByText(/Fixed a bug/)).toBeInTheDocument();
  });
});

// ── FilesTab ─────────────────────────────────────────────────────────────────

describe("FilesTab", () => {
  it("shows loading state initially", () => {
    mockFetch.mockReturnValue(new Promise(() => {})); // never resolves
    render(<FilesTab />);
    expect(screen.getByText("Loading files...")).toBeInTheDocument();
  });

  it("renders file list after fetch", async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      status: 200,
      json: () =>
        Promise.resolve([
          { file_path: "src/app.ts", session_count: 5 },
          { file_path: "src/utils.ts", session_count: 3 },
        ]),
    });

    await act(async () => {
      render(<FilesTab />);
    });

    expect(screen.getByText("src/app.ts")).toBeInTheDocument();
    expect(screen.getByText("src/utils.ts")).toBeInTheDocument();
    expect(screen.getByText("5")).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument();
  });

  it("shows empty state when no files", async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      status: 200,
      json: () => Promise.resolve([]),
    });

    await act(async () => {
      render(<FilesTab />);
    });

    expect(screen.getByText("No file data available.")).toBeInTheDocument();
  });

  it("shows error state on fetch failure", async () => {
    mockFetch.mockRejectedValue(new Error("fail"));

    await act(async () => {
      render(<FilesTab />);
    });

    expect(screen.getByText("Error loading files.")).toBeInTheDocument();
  });

  it("renders table headers", async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      status: 200,
      json: () =>
        Promise.resolve([{ file_path: "a.ts", session_count: 1 }]),
    });

    await act(async () => {
      render(<FilesTab />);
    });

    expect(screen.getByText("File path")).toBeInTheDocument();
    expect(screen.getByText("Sessions")).toBeInTheDocument();
    expect(screen.getByText("Frequency")).toBeInTheDocument();
  });
});
