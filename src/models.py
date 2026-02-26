"""Typed data models for the Copilot Dashboard."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TypedDict


@dataclass
class ProcessInfo:
    """Information about a running copilot process."""

    pid: int
    parent_pid: int = 0
    terminal_pid: int = 0
    terminal_name: str = ""
    cmdline: str = ""
    yolo: bool = False
    state: str = "unknown"
    waiting_context: str = ""
    bg_tasks: int = 0
    mcp_servers: list[str] = field(default_factory=list)


@dataclass
class EventData:
    """Parsed event data from a session's events.jsonl."""

    mcp_servers: list[str] = field(default_factory=list)
    tool_calls: int = 0
    subagent_runs: int = 0
    cwd: str = ""
    branch: str = ""
    repository: str = ""
    intent: str = ""


class SessionState(TypedDict):
    """State of a running session."""

    state: str  # 'waiting' | 'idle' | 'working' | 'thinking' | 'unknown'
    waiting_context: str
    bg_tasks: int


@dataclass
class VersionCache:
    """Cached PyPI version check result."""

    latest: str | None = None
    update_available: bool = False
    checked_at: float = 0.0


@dataclass
class RunningCache:
    """TTL cache for running session process data."""

    data: dict[str, ProcessInfo] = field(default_factory=dict)
    time: float = 0.0
