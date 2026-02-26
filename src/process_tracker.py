"""
Process and window tracker for Copilot CLI sessions.
Uses pywin32 to map running sessions to terminal windows and focus them.
Also detects session state (waiting/working), yolo mode, and MCP servers.
"""

import json
import logging
import os
import re
import subprocess
import sys
import threading
import time
from datetime import UTC, datetime

from .constants import (
    EVENT_STALENESS_THRESHOLD,
    EVENT_TAIL_BUFFER,
    MACOS_APP_NAMES,
    MACOS_FALLBACK_TERMINALS,
    MAX_ANCESTRY_DEPTH,
    MAX_DIAGNOSTICS_CHAIN,
    MAX_UNIX_PARENT_DEPTH,
    OSASCRIPT_TIMEOUT,
    OUTPUT_TAIL_BUFFER,
    PARENT_LOOKUP_TIMEOUT,
    POWERSHELL_TIMEOUT,
    PROCESS_MATCH_TOLERANCE,
    PS_TIMEOUT,
    RUNNING_CACHE_TTL,
    SESSION_STATE_DIR,
    TERMINAL_NAMES,
    UNIX_TERMINAL_SUBSTRINGS,
)
from .models import BackgroundTask, EventData, ProcessInfo, RunningCache, SessionState

logger = logging.getLogger(__name__)

EVENTS_DIR = SESSION_STATE_DIR

# Tool names that indicate "waiting for user input"
WAITING_TOOLS = frozenset({"ask_user", "ask_permission"})

# ---------------------------------------------------------------------------
# Caching layer
# ---------------------------------------------------------------------------
# TTL cache for get_running_sessions() — avoids repeated WMI/ps subprocess calls
_running_cache = RunningCache()
_running_lock = threading.Lock()

# Permanent cache for inactive session event data (mcp_servers, tool_counts,
# context, intent). Active sessions are re-read each poll; inactive ones are
# cached forever since their events.jsonl won't change.
_event_data_cache: dict[str, EventData] = {}


def _read_recent_events(session_id, count=10):
    """Read the last N events from a session's events.jsonl."""
    events_file = os.path.join(EVENTS_DIR, session_id, "events.jsonl")
    if not os.path.exists(events_file):
        return []
    try:
        with open(events_file, "rb") as f:
            f.seek(0, 2)
            size = f.tell()
            read_from = max(0, size - EVENT_TAIL_BUFFER)
            f.seek(read_from)
            chunk = f.read().decode("utf-8", errors="replace")
        raw_lines = [ln.strip() for ln in chunk.split("\n") if ln.strip()]
        # When seeking mid-file, the first line is likely truncated — discard it
        if read_from > 0 and raw_lines:
            raw_lines = raw_lines[1:]
        events = []
        for line in raw_lines[-count:]:
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                logger.debug("Skipping malformed event line in %s", session_id)
        return events
    except Exception as e:
        logger.debug("Error reading events for %s: %s", session_id, e)
        return []


def _get_session_state(session_id) -> SessionState:
    """
    Determine session state from events.jsonl.
    Returns a SessionState dict with state, waiting_context, and bg_tasks.
    """
    events = _read_recent_events(session_id, 30)
    if not events:
        return SessionState(state="unknown", waiting_context="", bg_tasks=0, bg_task_list=[])

    # Count running subagents from full file and extract task details
    events_file = os.path.join(EVENTS_DIR, session_id, "events.jsonl")
    bg = 0
    bg_task_list: list[BackgroundTask] = []
    try:
        with open(events_file, encoding="utf-8", errors="replace") as f:
            # Track started/completed subagents by toolCallId
            started: dict[str, BackgroundTask] = {}
            for line in f:
                if '"subagent.started"' in line:
                    try:
                        evt = json.loads(line)
                        data = evt.get("data", {})
                        tcid = data.get("toolCallId", "")
                        if tcid:
                            started[tcid] = BackgroundTask(
                                agent_name=data.get("agentDisplayName")
                                or data.get("agentName", ""),
                                description=data.get("agentDescription", ""),
                            )
                    except Exception:
                        pass
                elif '"subagent.completed"' in line:
                    try:
                        evt = json.loads(line)
                        tcid = evt.get("data", {}).get("toolCallId", "")
                        started.pop(tcid, None)
                    except Exception:
                        pass
            bg = len(started)
            bg_task_list = list(started.values())
    except Exception as e:
        logger.debug("Error counting subagents for %s: %s", session_id, e)

    # Track pending tool calls from recent events
    pending_tools = {}  # toolCallId -> event data
    for ev in events:
        etype = ev.get("type", "")
        data = ev.get("data", {})
        if etype == "tool.execution_start":
            tcid = data.get("toolCallId", "")
            if tcid:
                pending_tools[tcid] = data
        elif etype == "tool.execution_complete":
            tcid = data.get("toolCallId", "")
            pending_tools.pop(tcid, None)

    # Check pending tools: ask_user/ask_permission → waiting, anything else → working
    has_pending_work = False
    for _tcid, data in pending_tools.items():
        tool = data.get("toolName", "")
        if tool in WAITING_TOOLS:
            args = data.get("arguments", {})
            question = args.get("question", "")
            choices = args.get("choices", [])
            ctx = question
            if choices:
                ctx += " [" + " / ".join(choices[:4]) + "]"
            return SessionState(
                state="waiting", waiting_context=ctx, bg_tasks=bg, bg_task_list=bg_task_list
            )
        if tool != "report_intent":
            has_pending_work = True

    # If any non-trivial tools are still running, check if events are stale
    if has_pending_work:
        # Check timestamp of last event — if >60s old, events are likely buffered
        last_ts = events[-1].get("timestamp", "")
        if last_ts:
            try:
                evt_time = datetime.fromisoformat(last_ts.replace("Z", "+00:00"))
                age = (datetime.now(UTC) - evt_time).total_seconds()
                if age > EVENT_STALENESS_THRESHOLD:
                    return SessionState(
                        state="waiting",
                        waiting_context="Session likely waiting for input",
                        bg_tasks=bg,
                        bg_task_list=bg_task_list,
                    )
            except (ValueError, TypeError):
                pass
        return SessionState(
            state="working", waiting_context="", bg_tasks=bg, bg_task_list=bg_task_list
        )

    # Fall back to last event type
    last = events[-1]
    etype = last.get("type", "")
    data = last.get("data", {})

    if etype == "assistant.turn_end":
        return SessionState(
            state="idle",
            waiting_context="Session idle \u2014 waiting for user message",
            bg_tasks=bg,
            bg_task_list=bg_task_list,
        )
    if etype == "tool.execution_start":
        tool = data.get("toolName", "")
        if tool in WAITING_TOOLS:
            args = data.get("arguments", {})
            return SessionState(
                state="waiting",
                waiting_context=args.get("question", ""),
                bg_tasks=bg,
                bg_task_list=bg_task_list,
            )
        return SessionState(
            state="working", waiting_context="", bg_tasks=bg, bg_task_list=bg_task_list
        )
    if etype == "subagent.started":
        return SessionState(
            state="working", waiting_context="", bg_tasks=bg, bg_task_list=bg_task_list
        )
    if etype in (
        "tool.execution_complete",
        "subagent.completed",
        "assistant.turn_start",
        "assistant.message",
    ):
        return SessionState(
            state="thinking", waiting_context="", bg_tasks=bg, bg_task_list=bg_task_list
        )
    if etype == "user.message":
        return SessionState(
            state="thinking", waiting_context="", bg_tasks=bg, bg_task_list=bg_task_list
        )
    return SessionState(state="unknown", waiting_context="", bg_tasks=bg, bg_task_list=bg_task_list)


def _parse_mcp_servers(cmdline):
    """Extract MCP server names from --additional-mcp-config flag."""
    match = re.search(r"--additional-mcp-config\s+@?([^\s]+)", cmdline)
    if not match:
        return []
    config_path = match.group(1).strip('"').strip("'")
    try:
        with open(config_path, encoding="utf-8") as f:
            data = json.load(f)
        servers = data.get("mcpServers", {})
        return list(servers.keys())
    except Exception as e:
        logger.debug("Error parsing MCP config %s: %s", config_path, e)
        return []


def _parse_iso_timestamp(ts_str):
    """Parse an ISO 8601 timestamp."""
    return datetime.fromisoformat(ts_str)


def _match_process_to_session(creation_date_str):
    """Match a copilot.exe process (without --resume) to a session by creation time.

    Compares the process creation time to session.start timestamps in events.jsonl
    files. Returns the session ID with the closest match within a 10-second window.
    """
    try:
        proc_time = _parse_iso_timestamp(creation_date_str)
    except (ValueError, TypeError, AttributeError):
        return None

    if not os.path.isdir(EVENTS_DIR):
        return None

    best_sid = None
    best_delta = PROCESS_MATCH_TOLERANCE

    for sid in os.listdir(EVENTS_DIR):
        events_file = os.path.join(EVENTS_DIR, sid, "events.jsonl")
        if not os.path.exists(events_file):
            continue
        try:
            with open(events_file, encoding="utf-8", errors="replace") as f:
                first_line = f.readline().strip()
            if not first_line:
                continue
            evt = json.loads(first_line)
            if evt.get("type") not in ("session.start", "session.resume"):
                continue
            ts = evt.get("timestamp", "")
            if not ts:
                continue
            evt_time = _parse_iso_timestamp(ts)
            delta = abs((proc_time - evt_time).total_seconds())
            if delta < best_delta:
                best_delta = delta
                best_sid = sid
        except Exception as e:
            logger.debug("Error matching session %s: %s", sid, e)
            continue

    return best_sid


def _get_running_sessions_windows() -> dict[str, ProcessInfo]:
    """Find running copilot.exe processes on Windows via PowerShell/WMI."""
    # Get all processes once, then walk ancestry in Python
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
    except json.JSONDecodeError as e:
        logger.debug("Failed to parse PowerShell output: %s", e)
        return {}
    if isinstance(data, dict):
        data = [data]

    # Build a PID -> proc lookup for ancestry walking
    pid_map: dict = {p.get("ProcessId"): p for p in data if p.get("ProcessId")}

    def _find_terminal(start_pid: int) -> tuple:
        """Walk ancestors to find the nearest known terminal process."""
        visited = set()
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

    copilot_procs = [p for p in data if (p.get("Name") or "").lower() == "copilot.exe"]

    sessions: dict[str, ProcessInfo] = {}
    unmatched = []  # processes without --resume that need timestamp matching

    for proc in copilot_procs:
        cmd = proc.get("CommandLine", "")
        terminal_pid, terminal_name = _find_terminal(proc.get("ParentProcessId", 0))
        proc_info = ProcessInfo(
            pid=proc.get("ProcessId", 0),
            parent_pid=proc.get("ParentProcessId", 0),
            terminal_pid=terminal_pid,
            terminal_name=terminal_name,
            cmdline=cmd,
            yolo="--yolo" in cmd,
            mcp_servers=_parse_mcp_servers(cmd),
        )

        if "--resume" in cmd:
            parts = cmd.split("--resume")
            if len(parts) > 1:
                sid = parts[1].strip().lstrip("=").split()[0].strip('"').strip("'")
                sessions[sid] = proc_info
        else:
            # No --resume flag — try to match by creation time
            unmatched.append((proc, proc_info))

    # Match non-resume processes to sessions by creation timestamp
    for proc, proc_info in unmatched:
        created = proc.get("CreatedUTC", "")
        sid = _match_process_to_session(created)
        if sid:
            # Prefer this over a previously unmatched entry, but don't clobber --resume matches
            if sid not in sessions or "--resume" not in sessions[sid].cmdline:
                sessions[sid] = proc_info

    return sessions


def _get_running_sessions_unix() -> dict[str, ProcessInfo]:
    """Find running copilot processes on macOS/Linux via ps."""
    result = subprocess.run(
        ["ps", "axo", "pid,ppid,lstart,command"],
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
        # Match copilot binary (copilot or copilot.exe, or node ... copilot)
        if "copilot" not in line.lower():
            continue
        parts_line = line.split(None, 7)  # pid ppid lstart(5 fields) command
        if len(parts_line) < 8:
            continue
        try:
            pid = int(parts_line[0])
            ppid = int(parts_line[1])
        except (ValueError, IndexError):
            continue
        # lstart is like "Mon Feb 23 20:56:31 2026" (5 tokens)
        lstart_str = " ".join(parts_line[2:7])
        cmd = parts_line[7]

        # Walk up process tree to find terminal PID
        terminal_pid = 0
        terminal_name = ""
        try:
            cur_ppid = ppid
            for _ in range(MAX_UNIX_PARENT_DEPTH):
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
                # Check if this is a terminal application
                if any(t in pname for t in UNIX_TERMINAL_SUBSTRINGS):
                    terminal_pid = cur_ppid
                    terminal_name = pinfo[1].strip()
                    break
                cur_ppid = int(pinfo[0])
        except Exception as e:
            logger.debug("Error walking process tree from PID %d: %s", ppid, e)

        proc_info = ProcessInfo(
            pid=pid,
            parent_pid=ppid,
            terminal_pid=terminal_pid,
            terminal_name=terminal_name,
            cmdline=cmd,
            yolo="--yolo" in cmd,
            mcp_servers=_parse_mcp_servers(cmd),
        )

        if "--resume" in cmd:
            # Extract session ID from --resume <session_id>
            resume_parts = cmd.split("--resume")
            if len(resume_parts) >= 2:
                sid = resume_parts[1].strip().split()[0].strip('"').strip("'")
                if sid:
                    sessions[sid] = proc_info
                    continue
        # No --resume or couldn't extract session ID — try timestamp matching
        try:
            proc_time = datetime.strptime(lstart_str, "%a %b %d %H:%M:%S %Y")
            proc_time = proc_time.astimezone(UTC)
            sid = _match_process_to_session(proc_time.isoformat())
            if sid and sid not in sessions:
                sessions[sid] = proc_info
        except Exception as e:
            logger.debug("Error matching process to session by timestamp: %s", e)

    return sessions


def get_running_sessions() -> dict[str, ProcessInfo]:
    """
    Find running copilot processes and extract session info.
    Returns dict: {session_id: ProcessInfo}
    Uses a TTL cache to avoid repeated expensive WMI/ps subprocess calls.
    Lock is held across the entire operation so concurrent requests wait
    for the first one rather than each spawning their own subprocess.
    """
    with _running_lock:
        now = time.monotonic()
        if now - _running_cache.time < RUNNING_CACHE_TTL and _running_cache.data:
            return _running_cache.data
        try:
            if sys.platform == "win32":
                sessions = _get_running_sessions_windows()
            else:
                sessions = _get_running_sessions_unix()
            # Enrich each session with state info
            for sid, info in sessions.items():
                ss = _get_session_state(sid)
                info.state = ss["state"]
                info.waiting_context = ss["waiting_context"]
                info.bg_tasks = ss["bg_tasks"]
                info.bg_task_list = ss["bg_task_list"]
            _running_cache.data = sessions
            _running_cache.time = time.monotonic()
            return sessions
        except Exception as e:
            print(f"[process_tracker] Error scanning processes: {e}")
            logger.warning("Error scanning processes: %s", e)
            return _running_cache.data


def _read_event_data(session_id) -> EventData:
    """
    Read mcp_servers, tool_counts, context (cwd/branch/repo), and intent
    from a session's events.jsonl.  Returns an EventData dataclass.
    """
    result = EventData()
    events_file = os.path.join(EVENTS_DIR, session_id, "events.jsonl")
    if not os.path.exists(events_file):
        return result

    try:
        mcp_found = False
        last_intent = ""
        tool_count = 0
        sub_count = 0
        with open(events_file, encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue

                # Fast string pre-checks to avoid JSON parsing every line
                if ('"session.start"' in line or '"session.resume"' in line) and not result.cwd:
                    try:
                        evt = json.loads(line)
                        ctx = evt.get("data", {}).get("context", {})
                        result.cwd = ctx.get("cwd", "")
                        result.branch = ctx.get("branch", "")
                        result.repository = ctx.get("repository", "")
                    except json.JSONDecodeError:
                        pass
                    continue

                if not mcp_found and ('"infoType":"mcp"' in line or '"infoType": "mcp"' in line):
                    try:
                        evt = json.loads(line)
                        msg = evt.get("data", {}).get("message", "")
                        if "Configured MCP servers:" in msg:
                            names = msg.split("Configured MCP servers:")[-1].strip()
                            result.mcp_servers = [n.strip() for n in names.split(",") if n.strip()]
                        elif "GitHub MCP Server" in msg:
                            result.mcp_servers = ["github"]
                        elif msg:
                            result.mcp_servers = [msg]
                        mcp_found = True
                    except json.JSONDecodeError:
                        pass
                    continue

                if '"report_intent"' in line and '"tool.execution_start"' in line:
                    try:
                        evt = json.loads(line)
                        args = evt.get("data", {}).get("arguments", {})
                        if isinstance(args, str):
                            args = json.loads(args)
                        intent = args.get("intent", "")
                        if intent:
                            last_intent = intent
                    except (json.JSONDecodeError, TypeError):
                        pass
                    continue

                # Counting — lightweight string checks, no JSON needed
                if '"tool.execution_complete"' in line:
                    tool_count += 1
                if '"subagent.completed"' in line:
                    sub_count += 1

        result.tool_calls = tool_count
        result.subagent_runs = sub_count
        result.intent = last_intent
    except Exception as e:
        logger.debug("Error reading event data for %s: %s", session_id, e)

    return result


def _get_live_branch(cwd: str) -> str:
    """Read the current git branch directly from .git/HEAD (no subprocess)."""
    if not cwd:
        return ""
    try:
        head = os.path.join(cwd, ".git", "HEAD")
        if not os.path.exists(head):
            # Walk up to find the git root (handles worktrees pointing to main .git)
            parts = cwd.replace("\\", "/").split("/")
            for i in range(len(parts) - 1, 0, -1):
                candidate = "/".join(parts[:i]) + "/.git/HEAD"
                if os.path.exists(candidate):
                    head = candidate
                    break
        with open(head, encoding="utf-8") as f:
            line = f.read().strip()
        if line.startswith("ref: refs/heads/"):
            return line[len("ref: refs/heads/") :]
    except Exception as e:
        logger.debug("Error reading git HEAD for %s: %s", cwd, e)
    return ""


def get_session_event_data(session_id, is_running=False) -> EventData:
    """
    Get cached event data for a session.
    Active sessions are always re-read; inactive sessions use permanent cache.
    """
    if not is_running and session_id in _event_data_cache:
        return _event_data_cache[session_id]

    data = _read_event_data(session_id)

    # For running sessions, refresh branch from live .git/HEAD
    if is_running and data.cwd:
        live = _get_live_branch(data.cwd)
        if live:
            data.branch = live

    # Cache permanently for inactive sessions
    if not is_running:
        _event_data_cache[session_id] = data

    return data


def get_session_mcp_servers(session_id):
    """Extract MCP server names from a session's events.jsonl (works for past sessions)."""
    return get_session_event_data(session_id).mcp_servers


def get_recent_output(session_id, max_lines=10):
    """
    Extract the last N lines of meaningful tool output from events.jsonl.
    Keeps only the output from the *last* tool completion event (intentional).
    """
    events_file = os.path.join(EVENTS_DIR, session_id, "events.jsonl")
    if not os.path.exists(events_file):
        return []
    try:
        output_lines: list[str] = []
        with open(events_file, "rb") as f:
            f.seek(0, 2)
            size = f.tell()
            read_from = max(0, size - OUTPUT_TAIL_BUFFER)
            f.seek(read_from)
            chunk = f.read().decode("utf-8", errors="replace")

        for raw in chunk.split("\n"):
            raw = raw.strip()
            if not raw or "tool.execution_complete" not in raw:
                continue
            try:
                event = json.loads(raw)
                if event.get("type") != "tool.execution_complete":
                    continue
                content = event.get("data", {}).get("result", {}).get("content", "")
                if not content or len(content) < 5 or content.strip() == "Intent logged":
                    continue
                # Intentionally replace: we want the last tool's output only
                output_lines = content.strip().split("\n")
            except json.JSONDecodeError:
                continue

        return output_lines[-max_lines:] if output_lines else []
    except Exception as e:
        logger.debug("Error reading recent output for %s: %s", session_id, e)
        return []


def get_session_tool_counts(session_id):
    """Count tool calls and subagent runs for a session."""
    data = get_session_event_data(session_id)
    return data.tool_calls, data.subagent_runs


def _focus_session_window_windows(session_id, sessions: dict[str, ProcessInfo]):
    """Focus terminal window on Windows using pywin32."""
    try:
        import win32con
        import win32gui
        import win32process
    except ImportError:
        return False, "pywin32 not installed. Run: session_dashboard.py install"

    info = sessions[session_id]
    copilot_pid = info.pid
    terminal_pid = info.terminal_pid
    terminal_name = info.terminal_name

    # Build full ancestry chain for diagnostics
    def _get_ancestry(start_pid):
        chain = []
        pid = start_pid
        visited = set()
        for _ in range(MAX_DIAGNOSTICS_CHAIN):
            if pid in visited:
                break
            visited.add(pid)
            try:
                procs = subprocess.run(
                    [
                        "powershell",
                        "-NoProfile",
                        "-Command",
                        f"Get-CimInstance Win32_Process -Filter 'ProcessId={pid}' | "
                        f"Select-Object ProcessId,ParentProcessId,Name | ConvertTo-Json",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=PARENT_LOOKUP_TIMEOUT,
                    check=False,
                )
                p = json.loads(procs.stdout)
                if isinstance(p, list):
                    p = p[0]
                chain.append(f"  PID {p.get('ProcessId')} {p.get('Name')}")
                pid = p.get("ParentProcessId", 0)
                if not pid:
                    break
            except Exception:
                chain.append(f"  PID {pid} (lookup failed)")
                break
        return "\n".join(chain)

    tree = _get_ancestry(copilot_pid)
    diag = f"copilot PID={copilot_pid}, terminal_pid={terminal_pid} ({terminal_name})\nProcess tree:\n{tree}"

    if not terminal_pid:
        return False, f"Could not find terminal window.\n{diag}"

    target_hwnd = None

    def enum_cb(hwnd, _):
        nonlocal target_hwnd
        if win32gui.IsWindowVisible(hwnd):
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            if pid == terminal_pid:
                title = win32gui.GetWindowText(hwnd)
                if title:
                    target_hwnd = hwnd
        return True

    win32gui.EnumWindows(enum_cb, None)
    if not target_hwnd:
        return False, f"No visible window found for terminal PID {terminal_pid}.\n{diag}"

    try:
        import ctypes

        placement = win32gui.GetWindowPlacement(target_hwnd)
        if placement[1] == win32con.SW_SHOWMINIMIZED:
            win32gui.ShowWindow(target_hwnd, win32con.SW_RESTORE)

        fg_hwnd = win32gui.GetForegroundWindow()
        fg_thread = win32process.GetWindowThreadProcessId(fg_hwnd)[0]
        my_thread = win32process.GetWindowThreadProcessId(target_hwnd)[0]
        # windll is Windows-only; type: ignore keeps mypy happy on Linux
        user32 = ctypes.windll.user32  # type: ignore[attr-defined]
        if fg_thread != my_thread:
            user32.AttachThreadInput(fg_thread, my_thread, True)
            win32gui.SetForegroundWindow(target_hwnd)
            user32.AttachThreadInput(fg_thread, my_thread, False)
        else:
            win32gui.SetForegroundWindow(target_hwnd)
        title = win32gui.GetWindowText(target_hwnd)
        return True, f"Focused: {title}\n{diag}"
    except Exception as e:
        return False, f"Could not focus window: {e}\n{diag}"


def _focus_session_window_macos(session_id, sessions: dict[str, ProcessInfo]):
    """Focus terminal window on macOS using osascript."""
    info = sessions[session_id]
    terminal_name = info.terminal_name

    # Map process name to application name for AppleScript
    app_name = None
    tn = terminal_name.lower()
    for substring, name in MACOS_APP_NAMES.items():
        if substring in tn:
            app_name = name
            break

    if not app_name:
        # Fallback: use the first known terminal app
        for candidate in MACOS_FALLBACK_TERMINALS:
            app_name = candidate
            break

    if not app_name:
        return False, "Could not determine terminal application."

    # Validate app_name is in our known-safe allowlist to prevent injection
    allowed = set(MACOS_APP_NAMES.values()) | set(MACOS_FALLBACK_TERMINALS)
    if app_name not in allowed:
        return False, f"Unknown terminal application: {app_name}"

    try:
        script = f'tell application "{app_name}" to activate'
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=OSASCRIPT_TIMEOUT,
            check=False,
        )
        if result.returncode == 0:
            return True, f"Focused: {app_name}"
        return False, f"osascript failed: {result.stderr.strip()}"
    except Exception as e:
        return False, f"Could not focus window: {e}"


def focus_session_window(session_id):
    """
    Bring the terminal window running a session to the foreground.
    Returns (success: bool, message: str).
    """
    sessions = get_running_sessions()
    if session_id not in sessions:
        return False, "Session not found among running processes."

    if sys.platform == "win32":
        return _focus_session_window_windows(session_id, sessions)
    if sys.platform == "darwin":
        return _focus_session_window_macos(session_id, sessions)
    return False, "Window focus not supported on this platform."
