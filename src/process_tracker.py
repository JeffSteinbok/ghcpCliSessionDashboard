"""
Process and window tracker for Copilot CLI sessions.
Uses pywin32 to map running sessions to terminal windows and focus them.
Also detects session state (waiting/working), yolo mode, and MCP servers.
"""

import os
import sys
import subprocess
import json
import re
import time
import threading
from datetime import datetime, timezone


EVENTS_DIR = os.path.join(os.path.expanduser("~"), ".copilot", "session-state")

# ---------------------------------------------------------------------------
# Caching layer
# ---------------------------------------------------------------------------
# TTL cache for get_running_sessions() — avoids repeated WMI/ps subprocess calls
_running_cache = {"data": {}, "time": 0}
_RUNNING_CACHE_TTL = 5  # seconds
_running_lock = threading.Lock()

# Permanent cache for inactive session event data (mcp_servers, tool_counts,
# context, intent). Active sessions are re-read each poll; inactive ones are
# cached forever since their events.jsonl won't change.
_event_data_cache = {}  # session_id -> dict


def _read_recent_events(session_id, count=10):
    """Read the last N events from a session's events.jsonl."""
    events_file = os.path.join(EVENTS_DIR, session_id, "events.jsonl")
    if not os.path.exists(events_file):
        return []
    try:
        with open(events_file, "rb") as f:
            f.seek(0, 2)
            size = f.tell()
            read_from = max(0, size - 16384)
            f.seek(read_from)
            chunk = f.read().decode("utf-8", errors="replace")
        raw_lines = [l.strip() for l in chunk.split("\n") if l.strip()]
        events = []
        for line in raw_lines[-count:]:
            try:
                events.append(json.loads(line))
            except Exception:
                pass
        return events
    except Exception:
        return []


def _get_session_state(session_id):
    """
    Determine session state from events.jsonl.
    Returns: (state, waiting_context, running_bg_tasks)
      state: 'waiting' | 'idle' | 'working' | 'thinking' | 'unknown'
      waiting_context: str (question text if waiting/idle)
      running_bg_tasks: int count of background subagents currently running
    """
    events = _read_recent_events(session_id, 30)
    if not events:
        return "unknown", "", 0

    # Count running subagents from full file (fast string search)
    events_file = os.path.join(EVENTS_DIR, session_id, "events.jsonl")
    bg = 0
    try:
        with open(events_file, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
            bg = max(0, content.count('"subagent.started"') - content.count('"subagent.completed"'))
    except Exception:
        pass

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
    for tcid, data in pending_tools.items():
        tool = data.get("toolName", "")
        if tool in ("ask_user", "ask_permission"):
            args = data.get("arguments", {})
            question = args.get("question", "")
            choices = args.get("choices", [])
            ctx = question
            if choices:
                ctx += " [" + " / ".join(choices[:4]) + "]"
            return "waiting", ctx, bg
        if tool != "report_intent":
            has_pending_work = True

    # If any non-trivial tools are still running, check if events are stale
    if has_pending_work:
        # Check timestamp of last event — if >60s old, events are likely buffered
        last_ts = events[-1].get("timestamp", "")
        if last_ts:
            try:
                evt_time = datetime.fromisoformat(last_ts.replace("Z", "+00:00"))
                age = (datetime.now(timezone.utc) - evt_time).total_seconds()
                if age > 60:
                    return "waiting", "Session likely waiting for input", bg
            except (ValueError, TypeError):
                pass
        return "working", "", bg

    # Fall back to last event type
    last = events[-1]
    etype = last.get("type", "")
    data = last.get("data", {})

    if etype == "assistant.turn_end":
        return "idle", "Session idle \u2014 waiting for user message", bg
    if etype == "tool.execution_start":
        tool = data.get("toolName", "")
        if tool in ("ask_user", "ask_permission"):
            args = data.get("arguments", {})
            return "waiting", args.get("question", ""), bg
        return "working", "", bg
    if etype == "subagent.started":
        return "working", "", bg
    if etype in ("tool.execution_complete", "subagent.completed",
                 "assistant.turn_start", "assistant.message"):
        return "thinking", "", bg
    if etype == "user.message":
        return "thinking", "", bg
    return "unknown", "", bg


def _parse_mcp_servers(cmdline):
    """Extract MCP server names from --additional-mcp-config flag."""
    match = re.search(r'--additional-mcp-config\s+@?([^\s]+)', cmdline)
    if not match:
        return []
    config_path = match.group(1).strip('"').strip("'")
    try:
        with open(config_path, "r") as f:
            data = json.load(f)
        servers = data.get("mcpServers", {})
        return list(servers.keys())
    except Exception:
        return []


def _get_running_sessions_windows():
    """Find running copilot.exe processes on Windows via PowerShell/WMI."""
    ps_script = (
        "Get-CimInstance Win32_Process -Filter \"Name='copilot.exe'\" | "
        "Where-Object { $_.CommandLine -like '*--resume*' } | "
        "ForEach-Object { "
        "  $cpid = $_.ProcessId; $ppid = $_.ParentProcessId; $cmd = $_.CommandLine; "
        "  $parent = Get-CimInstance Win32_Process -Filter \"ProcessId=$ppid\" -EA SilentlyContinue; "
        "  $grandparent = if($parent){Get-CimInstance Win32_Process -Filter \"ProcessId=$($parent.ParentProcessId)\" -EA SilentlyContinue}; "
        "  $terminal = if($grandparent){Get-CimInstance Win32_Process -Filter \"ProcessId=$($grandparent.ParentProcessId)\" -EA SilentlyContinue}; "
        "  [PSCustomObject]@{ "
        "    PID=$cpid; PPID=$ppid; Cmd=$cmd; "
        "    ParentPID=if($parent){$parent.ProcessId}else{0}; "
        "    GrandparentPID=if($grandparent){$grandparent.ProcessId}else{0}; "
        "    TerminalPID=if($terminal){$terminal.ProcessId}else{0}; "
        "    TerminalName=if($terminal){$terminal.Name}else{''} "
        "  } "
        "} | ConvertTo-Json -Depth 3"
    )
    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command", ps_script],
        capture_output=True, text=True, timeout=10
    )
    if result.returncode != 0 or not result.stdout.strip():
        return {}

    data = json.loads(result.stdout)
    if isinstance(data, dict):
        data = [data]

    sessions = {}
    for proc in data:
        cmd = proc.get("Cmd", "")
        if "--resume" in cmd:
            parts = cmd.split("--resume")
            if len(parts) > 1:
                sid = parts[1].strip().split()[0].strip('"').strip("'")
                sessions[sid] = {
                    "pid": proc.get("PID"),
                    "parent_pid": proc.get("ParentPID"),
                    "grandparent_pid": proc.get("GrandparentPID"),
                    "terminal_pid": proc.get("TerminalPID"),
                    "terminal_name": proc.get("TerminalName", ""),
                    "cmdline": cmd,
                    "yolo": "--yolo" in cmd,
                    "mcp_servers": _parse_mcp_servers(cmd),
                }
    return sessions


def _get_running_sessions_unix():
    """Find running copilot processes on macOS/Linux via ps."""
    result = subprocess.run(
        ["ps", "axo", "pid,ppid,command"],
        capture_output=True, text=True, timeout=10
    )
    if result.returncode != 0 or not result.stdout.strip():
        return {}

    sessions = {}
    for line in result.stdout.strip().split("\n")[1:]:
        line = line.strip()
        if "--resume" not in line:
            continue
        # Match copilot binary (copilot or copilot.exe, or node ... copilot)
        if "copilot" not in line.lower():
            continue
        parts_line = line.split(None, 2)
        if len(parts_line) < 3:
            continue
        pid = int(parts_line[0])
        ppid = int(parts_line[1])
        cmd = parts_line[2]
        # Extract session ID from --resume <session_id>
        resume_parts = cmd.split("--resume")
        if len(resume_parts) < 2:
            continue
        sid = resume_parts[1].strip().split()[0].strip('"').strip("'")
        if not sid:
            continue
        # Walk up process tree to find terminal PID
        terminal_pid = 0
        terminal_name = ""
        try:
            cur_ppid = ppid
            for _ in range(5):
                parent_result = subprocess.run(
                    ["ps", "-p", str(cur_ppid), "-o", "ppid=,comm="],
                    capture_output=True, text=True, timeout=5
                )
                if parent_result.returncode != 0 or not parent_result.stdout.strip():
                    break
                pinfo = parent_result.stdout.strip().split(None, 1)
                if len(pinfo) < 2:
                    break
                pname = pinfo[1].strip().lower()
                # Check if this is a terminal application
                if any(t in pname for t in (
                    "terminal", "iterm", "alacritty", "kitty", "warp",
                    "hyper", "wezterm", "windowserver"
                )):
                    terminal_pid = cur_ppid
                    terminal_name = pinfo[1].strip()
                    break
                cur_ppid = int(pinfo[0])
        except Exception:
            pass
        sessions[sid] = {
            "pid": pid,
            "parent_pid": ppid,
            "grandparent_pid": 0,
            "terminal_pid": terminal_pid,
            "terminal_name": terminal_name,
            "cmdline": cmd,
            "yolo": "--yolo" in cmd,
            "mcp_servers": _parse_mcp_servers(cmd),
        }
    return sessions


def get_running_sessions():
    """
    Find running copilot processes and extract session info.
    Returns dict: {session_id: {pid, parent_pid, terminal_pid, cmdline,
                                yolo, state, mcp_servers}}
    Uses a TTL cache to avoid repeated expensive WMI/ps subprocess calls.
    Lock is held across the entire operation so concurrent requests wait
    for the first one rather than each spawning their own subprocess.
    """
    with _running_lock:
        now = time.monotonic()
        if now - _running_cache["time"] < _RUNNING_CACHE_TTL and _running_cache["data"]:
            return _running_cache["data"]
        try:
            if sys.platform == "win32":
                sessions = _get_running_sessions_windows()
            else:
                sessions = _get_running_sessions_unix()
            # Enrich each session with state info
            for sid in sessions:
                state, waiting_ctx, bg_tasks = _get_session_state(sid)
                sessions[sid]["state"] = state
                sessions[sid]["waiting_context"] = waiting_ctx
                sessions[sid]["bg_tasks"] = bg_tasks
            _running_cache["data"] = sessions
            _running_cache["time"] = time.monotonic()
            return sessions
        except Exception as e:
            print(f"[process_tracker] Error scanning processes: {e}")
            return {}


def _read_event_data(session_id):
    """
    Read mcp_servers, tool_counts, context (cwd/branch/repo), and intent
    from a session's events.jsonl.  Returns a dict with all fields.
    """
    result = {
        "mcp_servers": [],
        "tool_calls": 0,
        "subagent_runs": 0,
        "cwd": "",
        "branch": "",
        "repository": "",
        "intent": "",
    }
    events_file = os.path.join(EVENTS_DIR, session_id, "events.jsonl")
    if not os.path.exists(events_file):
        return result

    try:
        mcp_found = False
        last_intent = ""
        tool_count = 0
        sub_count = 0
        with open(events_file, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue

                # Fast string pre-checks to avoid JSON parsing every line
                if '"session.resume"' in line and not result["cwd"]:
                    try:
                        evt = json.loads(line)
                        ctx = evt.get("data", {}).get("context", {})
                        result["cwd"] = ctx.get("cwd", "")
                        result["branch"] = ctx.get("branch", "")
                        result["repository"] = ctx.get("repository", "")
                    except Exception:
                        pass
                    continue

                if not mcp_found and ('"infoType":"mcp"' in line
                                      or '"infoType": "mcp"' in line):
                    try:
                        evt = json.loads(line)
                        msg = evt.get("data", {}).get("message", "")
                        if "Configured MCP servers:" in msg:
                            names = msg.split("Configured MCP servers:")[-1].strip()
                            result["mcp_servers"] = [
                                n.strip() for n in names.split(",") if n.strip()
                            ]
                        elif "GitHub MCP Server" in msg:
                            result["mcp_servers"] = ["github"]
                        elif msg:
                            result["mcp_servers"] = [msg]
                        mcp_found = True
                    except Exception:
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
                    except Exception:
                        pass
                    continue

                # Counting — lightweight string checks, no JSON needed
                if '"tool.execution_complete"' in line:
                    tool_count += 1
                if '"subagent.completed"' in line:
                    sub_count += 1

        result["tool_calls"] = tool_count
        result["subagent_runs"] = sub_count
        result["intent"] = last_intent
    except Exception:
        pass

    return result


def get_session_event_data(session_id, is_running=False):
    """
    Get cached event data for a session.
    Active sessions are always re-read; inactive sessions use permanent cache.
    """
    if not is_running and session_id in _event_data_cache:
        return _event_data_cache[session_id]

    data = _read_event_data(session_id)

    # Cache permanently for inactive sessions
    if not is_running:
        _event_data_cache[session_id] = data

    return data


def get_session_mcp_servers(session_id):
    """Extract MCP server names from a session's events.jsonl (works for past sessions)."""
    return get_session_event_data(session_id).get("mcp_servers", [])


def get_recent_output(session_id, max_lines=10):
    """
    Extract the last N lines of meaningful tool output from events.jsonl.
    """
    events_file = os.path.join(EVENTS_DIR, session_id, "events.jsonl")
    if not os.path.exists(events_file):
        return []
    try:
        output_lines = []
        with open(events_file, "rb") as f:
            f.seek(0, 2)
            size = f.tell()
            read_from = max(0, size - 65536)
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
                output_lines = content.strip().split("\n")
            except Exception:
                continue

        return output_lines[-max_lines:] if output_lines else []
    except Exception:
        return []


def get_session_tool_counts(session_id):
    """Count tool calls and subagent runs for a session."""
    data = get_session_event_data(session_id)
    return data.get("tool_calls", 0), data.get("subagent_runs", 0)


def _focus_session_window_windows(session_id, sessions):
    """Focus terminal window on Windows using pywin32."""
    try:
        import win32gui
        import win32process
        import win32con
    except ImportError:
        return False, "pywin32 not installed. Run: session_dashboard.py install"

    info = sessions[session_id]
    terminal_pid = info.get("terminal_pid", 0)
    if not terminal_pid:
        return False, "Could not find terminal window for this session."

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
        return False, f"No visible window found for terminal PID {terminal_pid}."

    try:
        placement = win32gui.GetWindowPlacement(target_hwnd)
        if placement[1] == win32con.SW_SHOWMINIMIZED:
            win32gui.ShowWindow(target_hwnd, win32con.SW_RESTORE)
        win32gui.SetForegroundWindow(target_hwnd)
        title = win32gui.GetWindowText(target_hwnd)
        return True, f"Focused: {title}"
    except Exception as e:
        return False, f"Could not focus window: {e}"


def _focus_session_window_macos(session_id, sessions):
    """Focus terminal window on macOS using osascript."""
    info = sessions[session_id]
    terminal_name = info.get("terminal_name", "")
    pid = info.get("pid", 0)

    # Map process name to application name for AppleScript
    app_name = None
    tn = terminal_name.lower()
    if "iterm" in tn:
        app_name = "iTerm"
    elif "terminal" in tn:
        app_name = "Terminal"
    elif "alacritty" in tn:
        app_name = "Alacritty"
    elif "kitty" in tn:
        app_name = "kitty"
    elif "warp" in tn:
        app_name = "Warp"
    elif "wezterm" in tn:
        app_name = "WezTerm"

    if not app_name:
        # Fallback: try to find the frontmost terminal app that owns this PID
        for candidate in ["Terminal", "iTerm", "Warp"]:
            app_name = candidate
            break

    if not app_name:
        return False, "Could not determine terminal application."

    try:
        script = f'tell application "{app_name}" to activate'
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=5
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
    elif sys.platform == "darwin":
        return _focus_session_window_macos(session_id, sessions)
    else:
        return False, "Window focus not supported on this platform."
