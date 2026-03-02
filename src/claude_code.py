"""
Claude Code session reader for the Copilot Dashboard.

Reads session data from ~/.claude/projects/ (sessions-index.json + JSONL
transcripts) and detects running claude processes, mapping everything to
the same schema the dashboard uses for Copilot CLI sessions.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
from collections import Counter
from datetime import UTC, datetime

from .constants import (
    CLAUDE_PROJECTS_DIR,
    MAX_ANCESTRY_DEPTH,
    PARENT_LOOKUP_TIMEOUT,
    POWERSHELL_TIMEOUT,
    PS_TIMEOUT,
    TERMINAL_NAMES,
    UNIX_TERMINAL_SUBSTRINGS,
)
from .grouping import get_group_name
from .models import ProcessInfo

logger = logging.getLogger(__name__)

# Prefix to namespace Claude session IDs and avoid collisions with Copilot UUIDs
SESSION_ID_PREFIX = "cc:"

CLAUDE_PROCESS_NAMES: frozenset[str] = frozenset({"claude.exe", "claude"})


def _time_ago(iso_str: str | None) -> str:
    """Convert an ISO timestamp to a human-readable relative time string."""
    if not iso_str:
        return "unknown"
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        now = datetime.now(UTC)
        seconds = int((now - dt).total_seconds())
        if seconds < 60:
            return f"{seconds}s ago"
        if seconds < 3600:
            return f"{seconds // 60}m ago"
        if seconds < 86400:
            return f"{seconds // 3600}h ago"
        return f"{seconds // 86400}d ago"
    except Exception:
        return iso_str or "unknown"


# ── Session listing ──────────────────────────────────────────────────────────


def get_claude_sessions(
    running: dict[str, ProcessInfo] | None = None,
) -> list[dict]:
    """Read all Claude Code sessions from sessions-index.json files.

    Returns a list of dicts matching the SessionResponse schema.
    """
    if not os.path.isdir(CLAUDE_PROJECTS_DIR):
        return []

    if running is None:
        running = {}

    sessions: list[dict] = []
    for project_dir_name in os.listdir(CLAUDE_PROJECTS_DIR):
        project_path = os.path.join(CLAUDE_PROJECTS_DIR, project_dir_name)
        if not os.path.isdir(project_path):
            continue
        index_file = os.path.join(project_path, "sessions-index.json")
        if not os.path.exists(index_file):
            continue
        try:
            with open(index_file, encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            logger.debug("Error reading %s: %s", index_file, e)
            continue

        for entry in data.get("entries", []):
            sid = entry.get("sessionId", "")
            if not sid:
                continue
            prefixed_id = SESSION_ID_PREFIX + sid
            proc = running.get(prefixed_id)

            created = entry.get("created", "")
            modified = entry.get("modified", "") or created
            cwd = entry.get("projectPath", "")

            s: dict = {
                "id": prefixed_id,
                "cwd": cwd,
                "repository": _derive_repository(cwd),
                "branch": entry.get("gitBranch", "") or "",
                "summary": entry.get("summary") or entry.get("firstPrompt") or "",
                "created_at": created,
                "updated_at": modified,
                "created_ago": _time_ago(created),
                "time_ago": _time_ago(modified),
                "turn_count": entry.get("messageCount", 0),
                "file_count": 0,
                "checkpoint_count": 0,
                "is_running": proc is not None,
                "state": proc.state if proc else None,
                "waiting_context": proc.waiting_context if proc else "",
                "bg_tasks": proc.bg_tasks if proc else 0,
                "recent_activity": "",
                "restart_cmd": _build_restart_cmd(sid, cwd),
                "mcp_servers": [],
                "tool_calls": 0,
                "subagent_runs": 0,
                "intent": "",
                "source": "claude",
            }
            s["group"] = get_group_name(s)
            sessions.append(s)

    return sessions


def _derive_repository(cwd: str) -> str:
    """Try to derive a repository name from the project path."""
    if not cwd:
        return ""
    git_dir = os.path.join(cwd, ".git")
    if os.path.isdir(git_dir):
        # Read .git/config for remote URL, or just use dir name
        return os.path.basename(cwd)
    return ""


def _build_restart_cmd(session_id: str, cwd: str) -> str:
    """Build a restart command for a Claude Code session."""
    parts: list[str] = []
    if cwd:
        parts.append(f'cd "{cwd}" &&')
    parts.append(f"claude --resume {session_id}")
    return " ".join(parts)


# ── Session detail ───────────────────────────────────────────────────────────


def get_claude_session_detail(session_id: str) -> dict:
    """Read detailed info for a single Claude Code session.

    Parses the transcript JSONL to extract turns and tool counts.
    session_id should be the raw ID (without the cc: prefix).
    """
    result: dict = {
        "checkpoints": [],
        "refs": [],
        "turns": [],
        "recent_output": [],
        "tool_counts": [],
        "files": [],
    }

    transcript = _find_transcript(session_id)
    if not transcript:
        return result

    turns: list[dict] = []
    tool_counter: Counter = Counter()
    files_seen: set[str] = set()
    turn_index = 0

    try:
        with open(transcript, encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line)
                except json.JSONDecodeError:
                    continue

                msg_type = msg.get("type", "")
                message = msg.get("message", {})
                content = message.get("content", "")

                if msg_type == "user" and not msg.get("isMeta"):
                    text = _extract_text(content)
                    if text:
                        turns.append(
                            {
                                "turn_index": turn_index,
                                "user_message": text,
                                "assistant_response": None,
                            }
                        )
                        turn_index += 1

                elif msg_type == "assistant":
                    text = _extract_text(content)
                    tools = _extract_tool_uses(content)
                    for tool_name in tools:
                        tool_counter[tool_name] += 1
                    for _tool_name, tool_input in _extract_tool_details(content):
                        fp = tool_input.get("file_path", "")
                        if fp:
                            files_seen.add(fp)
                    if text:
                        turns.append(
                            {
                                "turn_index": turn_index,
                                "user_message": None,
                                "assistant_response": text,
                            }
                        )
                        turn_index += 1
    except Exception as e:
        logger.debug("Error reading Claude transcript %s: %s", transcript, e)

    # Return last 10 turns like Copilot detail does
    result["turns"] = turns[-10:]
    result["tool_counts"] = [{"name": k, "count": v} for k, v in tool_counter.most_common(10)]
    result["files"] = sorted(files_seen)
    return result


def _find_transcript(session_id: str) -> str | None:
    """Find the JSONL transcript file for a Claude Code session."""
    if not os.path.isdir(CLAUDE_PROJECTS_DIR):
        return None
    for project_dir_name in os.listdir(CLAUDE_PROJECTS_DIR):
        project_path = os.path.join(CLAUDE_PROJECTS_DIR, project_dir_name)
        if not os.path.isdir(project_path):
            continue
        candidate = os.path.join(project_path, f"{session_id}.jsonl")
        if os.path.exists(candidate):
            return candidate
    return None


def _extract_text(content) -> str:
    """Extract plain text from message content (string or content blocks)."""
    if isinstance(content, str):
        # Skip meta/command messages
        if content.startswith("<local-command-caveat>") or content.startswith("<command-name>"):
            return ""
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
        return "\n".join(parts)
    return ""


def _extract_tool_uses(content) -> list[str]:
    """Extract tool names from content blocks."""
    if not isinstance(content, list):
        return []
    return [
        block.get("name", "")
        for block in content
        if isinstance(block, dict) and block.get("type") == "tool_use"
    ]


def _extract_tool_details(content) -> list[tuple[str, dict]]:
    """Extract (tool_name, input_dict) from content blocks."""
    if not isinstance(content, list):
        return []
    return [
        (block.get("name", ""), block.get("input", {}))
        for block in content
        if isinstance(block, dict) and block.get("type") == "tool_use"
    ]


# ── Process detection ────────────────────────────────────────────────────────


def get_running_claude_sessions() -> dict[str, ProcessInfo]:
    """Detect running Claude Code processes and match to sessions.

    Returns dict: {prefixed_session_id: ProcessInfo}
    """
    try:
        if sys.platform == "win32":
            return _get_running_claude_windows()
        return _get_running_claude_unix()
    except Exception as e:
        logger.warning("Error scanning Claude processes: %s", e)
        return {}


def _get_running_claude_windows() -> dict[str, ProcessInfo]:
    """Find running claude.exe processes on Windows via PowerShell/WMI."""
    ps_script = (
        "Get-CimInstance Win32_Process | "
        "Select-Object ProcessId,ParentProcessId,Name,CommandLine,"
        "@{N='CreatedUTC';E={$_.CreationDate.ToUniversalTime().ToString('o')}} | "
        "ConvertTo-Json -Depth 2"
    )
    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command", ps_script],
        capture_output=True,
        text=True,
        timeout=POWERSHELL_TIMEOUT,
        check=False,
    )
    if result.returncode != 0 or not result.stdout.strip():
        return {}

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        return {}
    if isinstance(data, dict):
        data = [data]

    pid_map: dict = {p.get("ProcessId"): p for p in data if p.get("ProcessId")}

    def _find_terminal(start_pid: int) -> tuple[int, str]:
        visited: set[int] = set()
        pid = start_pid
        for _ in range(MAX_ANCESTRY_DEPTH):
            proc = pid_map.get(pid)
            if not proc:
                break
            name = (proc.get("Name") or "").lower()
            if name in TERMINAL_NAMES:
                return proc.get("ProcessId", 0), proc.get("Name", "")
            ppid = proc.get("ParentProcessId", 0)
            if ppid == 0 or ppid in visited:
                break
            visited.add(pid)
            pid = ppid
        return 0, ""

    claude_procs = [p for p in data if (p.get("Name") or "").lower() in CLAUDE_PROCESS_NAMES]

    sessions: dict[str, ProcessInfo] = {}
    for proc in claude_procs:
        cmd = proc.get("CommandLine", "")
        terminal_pid, terminal_name = _find_terminal(proc.get("ParentProcessId", 0))
        proc_info = ProcessInfo(
            pid=proc.get("ProcessId", 0),
            parent_pid=proc.get("ParentProcessId", 0),
            terminal_pid=terminal_pid,
            terminal_name=terminal_name,
            cmdline=cmd,
        )
        # Claude Code uses --resume <session_id>
        if "--resume" in cmd:
            parts = cmd.split("--resume")
            if len(parts) > 1:
                sid = parts[1].strip().lstrip("=").split()[0].strip('"').strip("'")
                sessions[SESSION_ID_PREFIX + sid] = proc_info

    return sessions


def _get_running_claude_unix() -> dict[str, ProcessInfo]:
    """Find running claude processes on macOS/Linux via ps."""
    result = subprocess.run(
        ["ps", "axo", "pid,ppid,command"],
        capture_output=True,
        text=True,
        timeout=PS_TIMEOUT,
        check=False,
    )
    if result.returncode != 0 or not result.stdout.strip():
        return {}

    sessions: dict[str, ProcessInfo] = {}
    for line in result.stdout.strip().split("\n")[1:]:
        line = line.strip()
        if "claude" not in line.lower():
            continue
        parts = line.split(None, 2)
        if len(parts) < 3:
            continue
        try:
            pid = int(parts[0])
            ppid = int(parts[1])
        except (ValueError, IndexError):
            continue
        cmd = parts[2]

        # Walk up process tree to find terminal PID
        terminal_pid = 0
        terminal_name = ""
        try:
            cur_ppid = ppid
            for _ in range(5):
                parent_result = subprocess.run(
                    ["ps", "-p", str(cur_ppid), "-o", "ppid=,comm="],
                    capture_output=True,
                    text=True,
                    timeout=PARENT_LOOKUP_TIMEOUT,
                    check=False,
                )
                if parent_result.returncode != 0 or not parent_result.stdout.strip():
                    break
                pinfo = parent_result.stdout.strip().split(None, 1)
                if len(pinfo) < 2:
                    break
                pname = pinfo[1].strip().lower()
                if any(t in pname for t in UNIX_TERMINAL_SUBSTRINGS):
                    terminal_pid = cur_ppid
                    terminal_name = pinfo[1].strip()
                    break
                cur_ppid = int(pinfo[0])
        except Exception:
            pass

        proc_info = ProcessInfo(
            pid=pid,
            parent_pid=ppid,
            terminal_pid=terminal_pid,
            terminal_name=terminal_name,
            cmdline=cmd,
        )

        if "--resume" in cmd:
            resume_parts = cmd.split("--resume")
            if len(resume_parts) >= 2:
                sid = resume_parts[1].strip().split()[0].strip('"').strip("'")
                if sid:
                    sessions[SESSION_ID_PREFIX + sid] = proc_info

    return sessions
