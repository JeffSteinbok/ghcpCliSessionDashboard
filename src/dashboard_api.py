"""
Copilot Dashboard — FastAPI web application.

Serves a real-time dashboard of all Copilot CLI sessions with:
  - Active vs Previous session split
  - Project-area grouping
  - Restart commands with copy buttons
  - Click-to-focus terminal windows
  - Light/dark mode and palette selector
  - Auto-generated OpenAPI docs at /docs
"""

import json
import os
import re
import signal
import sqlite3
import subprocess
import sys
import time
import urllib.request
from collections import Counter
from dataclasses import asdict
from datetime import UTC, datetime

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from .__version__ import __version__
from .constants import (
    PYPI_FETCH_TIMEOUT,
    PYPI_PACKAGE_URL,
    RECENT_ACTIVITY_MAX_LEN,
    SECONDS_PER_DAY,
    SECONDS_PER_HOUR,
    SECONDS_PER_MINUTE,
    SESSION_STATE_DIR,
    SESSION_STORE_DB,
    VERSION_CACHE_TTL,
)
from .grouping import get_group_name
from .models import EventData, ProcessInfo, VersionCache
from .process_tracker import (
    focus_session_window,
    get_recent_output,
    get_running_sessions,
    get_session_event_data,
)
from .schemas import (
    ActionResponse,
    FileEntryResponse,
    ProcessResponse,
    ServerInfoResponse,
    SessionDetailResponse,
    SessionResponse,
    VersionResponse,
)

# ── App setup ────────────────────────────────────────────────────────────────

PKG_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(PKG_DIR, "static")
DIST_DIR = os.path.join(STATIC_DIR, "dist")
TEMPLATES_DIR = os.path.join(PKG_DIR, "templates")

app = FastAPI(
    title="Copilot Dashboard",
    version=__version__,
    description="Monitor all your GitHub Copilot CLI sessions in real-time.",
)

# Mount /static for legacy assets (favicon, icons, etc.)
if os.path.isdir(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

DB_PATH = SESSION_STORE_DB
_version_cache = VersionCache()


# ── Helpers ──────────────────────────────────────────────────────────────────


def get_db() -> sqlite3.Connection:
    """Open the session-store database in read-only mode."""
    if not os.path.exists(DB_PATH):
        raise FileNotFoundError(
            f"Session store not found at {DB_PATH}. "
            "Enable the SESSION_STORE experimental feature by adding "
            '"experimental": true to ~/.copilot/config.json, '
            "then start a new Copilot session."
        )
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def time_ago(iso_str: str | None) -> str:
    """Convert an ISO timestamp to a human-readable relative time string."""
    if not iso_str:
        return "unknown"
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        now = datetime.now(UTC)
        seconds = int((now - dt).total_seconds())
        if seconds < SECONDS_PER_MINUTE:
            return f"{seconds}s ago"
        if seconds < SECONDS_PER_HOUR:
            return f"{seconds // SECONDS_PER_MINUTE}m ago"
        if seconds < SECONDS_PER_DAY:
            return f"{seconds // SECONDS_PER_HOUR}h ago"
        return f"{seconds // SECONDS_PER_DAY}d ago"
    except Exception:
        return iso_str


def get_recent_activity(session: dict) -> str:
    """Short description of recent activity from the latest checkpoint."""
    last_cp_title = session.get("last_cp_title") or ""
    last_cp_overview = session.get("last_cp_overview") or ""
    summary = session.get("summary") or ""

    if last_cp_title and last_cp_title.lower() != summary.lower():
        return last_cp_title
    if last_cp_overview:
        first_sentence = last_cp_overview.split(". ")[0]
        if len(first_sentence) > RECENT_ACTIVITY_MAX_LEN:
            return first_sentence[: RECENT_ACTIVITY_MAX_LEN - 3] + "..."
        return first_sentence
    return ""


def _extract_extra_args(cmdline: str) -> str:
    """Extract extra CLI arguments from a copilot process command line."""
    if not cmdline:
        return ""
    import shlex

    try:
        parts = shlex.split(cmdline, posix=(os.name != "nt"))
    except ValueError:
        parts = cmdline.split()

    start = 0
    for i, p in enumerate(parts):
        if "copilot" in p.lower():
            start = i + 1
            break

    extra: list[str] = []
    skip_next = False
    for p in parts[start:]:
        if skip_next:
            skip_next = False
            continue
        if p == "--resume":
            skip_next = True
            continue
        extra.append(p)
    return " ".join(extra)


def build_restart_command(session: dict, yolo: bool = False, cmdline: str = "") -> str:
    """Build a restart command for a session."""
    sid = session["id"]
    cwd = session.get("cwd") or ""
    parts: list[str] = []
    if cwd:
        parts.append(f'cd "{cwd}" &&')
    cmd = f"copilot --resume {sid}"
    extra = _extract_extra_args(cmdline)
    if extra:
        cmd += " " + extra
    elif yolo:
        cmd += " --yolo"
    parts.append(cmd)
    return " ".join(parts)


# ── Session query helpers ────────────────────────────────────────────────────

_SESSIONS_QUERY = """
    SELECT
        s.id, s.cwd, s.repository, s.branch, s.summary,
        s.created_at, s.updated_at,
        (SELECT COUNT(*) FROM turns t WHERE t.session_id = s.id) as turn_count,
        (SELECT COUNT(*) FROM session_files sf WHERE sf.session_id = s.id) as file_count,
        (SELECT COUNT(*) FROM checkpoints cp WHERE cp.session_id = s.id) as checkpoint_count,
        (SELECT user_message FROM turns t WHERE t.session_id = s.id AND t.turn_index = 0) as first_msg,
        (SELECT title FROM checkpoints c WHERE c.session_id = s.id ORDER BY checkpoint_number DESC LIMIT 1) as last_cp_title,
        (SELECT overview FROM checkpoints c WHERE c.session_id = s.id ORDER BY checkpoint_number DESC LIMIT 1) as last_cp_overview
    FROM sessions s
    ORDER BY s.updated_at DESC
"""


def _enrich_session(s: dict, proc: ProcessInfo | None, evt: EventData) -> dict:
    """Enrich a raw session row with computed fields."""
    s["time_ago"] = time_ago(s["updated_at"])
    s["created_ago"] = time_ago(s["created_at"])
    is_running = proc is not None
    s["is_running"] = is_running

    if proc:
        s["state"] = proc.state
        s["waiting_context"] = proc.waiting_context
        s["bg_tasks"] = proc.bg_tasks
    else:
        s["state"] = None
        s["waiting_context"] = ""
        s["bg_tasks"] = 0

    # Backfill cwd/branch/repo from events when SQL has NULLs
    if not s.get("cwd") and evt.cwd:
        s["cwd"] = evt.cwd
    if not s.get("branch") and evt.branch:
        s["branch"] = evt.branch
    if not s.get("repository") and evt.repository:
        s["repository"] = evt.repository

    s["group"] = get_group_name(s)
    s["recent_activity"] = get_recent_activity(s)
    s["restart_cmd"] = build_restart_command(
        s, yolo=proc.yolo if proc else False, cmdline=proc.cmdline if proc else ""
    )
    s["mcp_servers"] = proc.mcp_servers if proc else evt.mcp_servers
    s["tool_calls"] = evt.tool_calls
    s["subagent_runs"] = evt.subagent_runs
    s["intent"] = evt.intent

    # Don't send large text fields to the client
    s.pop("first_msg", None)
    s.pop("last_cp_overview", None)
    s.pop("last_cp_title", None)
    return s


# ── API Routes ───────────────────────────────────────────────────────────────


@app.get("/api/sessions", response_model=list[SessionResponse])
def api_sessions():
    """List all sessions with enriched metadata."""
    try:
        db = get_db()
    except FileNotFoundError as e:
        return JSONResponse({"error": str(e)}, status_code=503)
    rows = db.execute(_SESSIONS_QUERY).fetchall()
    db.close()

    running = get_running_sessions()
    result = []
    for r in rows:
        s = dict(r)
        proc = running.get(s["id"])
        evt = get_session_event_data(s["id"], is_running=proc is not None)
        result.append(_enrich_session(s, proc, evt))
    return result


@app.get("/api/session/{session_id}", response_model=SessionDetailResponse)
def api_session_detail(session_id: str):
    """Get detailed info for a single session."""
    try:
        db = get_db()
    except FileNotFoundError as e:
        return JSONResponse({"error": str(e)}, status_code=503)
    checkpoints = db.execute(
        "SELECT checkpoint_number, title, overview, next_steps "
        "FROM checkpoints WHERE session_id = ? ORDER BY checkpoint_number",
        (session_id,),
    ).fetchall()
    refs = db.execute(
        "SELECT ref_type, ref_value FROM session_refs WHERE session_id = ?",
        (session_id,),
    ).fetchall()
    turns = db.execute(
        "SELECT turn_index, user_message, assistant_response "
        "FROM turns WHERE session_id = ? ORDER BY turn_index DESC LIMIT 10",
        (session_id,),
    ).fetchall()
    files = db.execute(
        "SELECT DISTINCT file_path FROM session_files WHERE session_id = ? ORDER BY file_path",
        (session_id,),
    ).fetchall()
    db.close()

    # Read tool counts from events.jsonl
    events_file = os.path.join(SESSION_STATE_DIR, session_id, "events.jsonl")
    tool_counter: Counter = Counter()
    if os.path.exists(events_file):
        try:
            with open(events_file, encoding="utf-8", errors="replace") as f:
                for line in f:
                    if '"tool.execution_start"' in line:
                        try:
                            evt = json.loads(line)
                            if evt.get("type") == "tool.execution_start":
                                tool_name = evt.get("data", {}).get("toolName", "")
                                if tool_name:
                                    tool_counter[tool_name] += 1
                        except Exception:
                            pass
        except Exception:
            pass
    tool_counts = [{"name": k, "count": v} for k, v in tool_counter.most_common(10)]

    return {
        "checkpoints": [dict(r) for r in checkpoints],
        "refs": [dict(r) for r in refs],
        "turns": [dict(r) for r in reversed(list(turns))],
        "recent_output": get_recent_output(session_id),
        "tool_counts": tool_counts,
        "files": [r["file_path"] for r in files],
    }


@app.get("/api/files", response_model=list[FileEntryResponse])
def api_files():
    """Return most-edited files across all sessions."""
    try:
        db = get_db()
    except FileNotFoundError as e:
        return JSONResponse({"error": str(e)}, status_code=503)
    rows = db.execute("""
        SELECT sf.file_path, COUNT(DISTINCT sf.session_id) as session_count,
        GROUP_CONCAT(DISTINCT sf.session_id) as session_ids
        FROM session_files sf GROUP BY sf.file_path
        ORDER BY session_count DESC LIMIT 100
    """).fetchall()
    db.close()
    return [dict(r) for r in rows]


@app.get("/api/processes", response_model=dict[str, ProcessResponse])
def api_processes():
    """Return currently running copilot sessions mapped by session ID."""
    return {sid: asdict(info) for sid, info in get_running_sessions().items()}


@app.post("/api/kill/{session_id:path}", response_model=ActionResponse)
def api_kill(session_id: str):
    """Kill the process for a running session."""
    running = get_running_sessions()
    if session_id not in running:
        return JSONResponse(
            {"success": False, "message": "Session not found among running processes"},
            status_code=404,
        )
    pid = running[session_id].pid
    if not pid:
        return JSONResponse({"success": False, "message": "PID not available"}, status_code=404)
    try:
        if sys.platform == "win32":
            subprocess.run(["taskkill", "/F", "/PID", str(pid)], check=True, capture_output=True)
        else:
            os.kill(pid, signal.SIGTERM)
        return {"success": True, "message": f"Killed PID {pid}"}
    except Exception as e:
        return JSONResponse({"success": False, "message": str(e)}, status_code=500)


@app.post("/api/focus/{session_id}", response_model=ActionResponse)
def api_focus(session_id: str):
    """Focus the terminal window for a running session."""
    success, message = focus_session_window(session_id)
    return {"success": success, "message": message}


@app.get("/api/server-info", response_model=ServerInfoResponse)
def server_info(request: Request):
    """Return server metadata including PID."""
    host = request.headers.get("host", "localhost:5111")
    return {"pid": os.getpid(), "port": host.split(":")[-1]}


@app.get("/api/version", response_model=VersionResponse)
def api_version():
    """Return current version and check PyPI for the latest release."""
    now = time.monotonic()
    if _version_cache.latest is not None and now - _version_cache.checked_at < VERSION_CACHE_TTL:
        return {
            "current": __version__,
            "latest": _version_cache.latest,
            "update_available": _version_cache.update_available,
        }

    try:
        with urllib.request.urlopen(PYPI_PACKAGE_URL, timeout=PYPI_FETCH_TIMEOUT) as resp:
            data = json.loads(resp.read())

        def _ver(v: str) -> tuple:
            """Parse a PEP 440-ish version into a comparable tuple."""
            m = re.match(r"(\d+(?:\.\d+)*)", v)
            if not m:
                return (0, 0, 0, 0)
            nums = tuple(int(x) for x in m.group(1).split("."))
            # Pre-release (a/b/rc) sorts before the final release
            pre = 0 if re.search(r"(a|b|rc)\d*$", v) else 1
            return (*nums, pre)

        def _is_prerelease(v: str) -> bool:
            return bool(re.search(r"(a|b|rc|dev)\d*$", v))

        if _is_prerelease(__version__):
            # On a pre-release: consider all versions (including pre-releases)
            latest = max(data.get("releases", {}), key=_ver, default=__version__)
        else:
            # On stable: only offer stable upgrades
            latest = data["info"]["version"]

        update_available = _ver(latest) > _ver(__version__)
    except Exception:
        latest = __version__
        update_available = False

    _version_cache.latest = latest
    _version_cache.update_available = update_available
    _version_cache.checked_at = now
    return {
        "current": __version__,
        "latest": latest,
        "update_available": update_available,
    }


@app.post("/api/update", response_model=ActionResponse)
def api_update(request: Request):
    """Spawn a detached subprocess to pip-upgrade the package and restart."""
    host = request.headers.get("host", "localhost:5111")
    port = host.split(":")[-1]
    server_pid = os.getpid()

    script_lines = [
        "import subprocess, sys, os, signal, time, shutil",
        "time.sleep(2)",
        "subprocess.run([sys.executable, '-m', 'pip', 'install', '--upgrade', 'ghcp-cli-dashboard'],"
        " check=False, capture_output=True)",
        f"pid = {server_pid}",
        "try:",
        "    if sys.platform == 'win32':",
        "        subprocess.run(['taskkill', '/F', '/PID', str(pid)], capture_output=True, check=False)",
        "    else:",
        "        os.kill(pid, signal.SIGTERM)",
        "except Exception:",
        "    pass",
        "time.sleep(1)",
        "cmd = shutil.which('copilot-dashboard')",
        "if cmd:",
        "    kw = {'stdout': subprocess.DEVNULL, 'stderr': subprocess.DEVNULL}",
        "    if sys.platform == 'win32':",
        "        kw['creationflags'] = subprocess.CREATE_NO_WINDOW | 0x8",
        "    else:",
        "        kw['start_new_session'] = True",
        f"    subprocess.Popen([cmd, 'start', '--background', '--port', '{port}'], **kw)",
    ]
    script = "\n".join(script_lines)

    kwargs: dict = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
    if sys.platform == "win32":
        kwargs["creationflags"] = 0x08000000 | 0x00000008  # CREATE_NO_WINDOW | DETACHED_PROCESS
    else:
        kwargs["start_new_session"] = True

    subprocess.Popen([sys.executable, "-c", script], **kwargs)
    return {
        "success": True,
        "message": "Update started. Server will restart shortly.",
    }


# ── PWA / static routes ─────────────────────────────────────────────────────


@app.get("/favicon.png", include_in_schema=False)
def favicon():
    """Serve the Copilot favicon."""
    path = os.path.join(STATIC_DIR, "favicon.png")
    if os.path.exists(path):
        return FileResponse(path, media_type="image/png")
    return Response(status_code=404)


@app.get("/manifest.json", include_in_schema=False)
def manifest():
    """PWA web app manifest — enables 'Install app' in Chrome/Edge."""
    data = {
        "name": "Copilot Dashboard",
        "short_name": "Copilot",
        "description": "Monitor all your GitHub Copilot CLI sessions in real-time.",
        "start_url": "/",
        "scope": "/",
        "display": "standalone",
        "background_color": "#0d1117",
        "theme_color": "#0d1117",
        "icons": [
            {"src": "/favicon.png", "sizes": "64x64", "type": "image/png"},
            {
                "src": "/static/icon-192.png",
                "sizes": "192x192",
                "type": "image/png",
                "purpose": "any maskable",
            },
            {
                "src": "/static/icon-512.png",
                "sizes": "512x512",
                "type": "image/png",
                "purpose": "any maskable",
            },
        ],
    }
    return JSONResponse(data)


@app.get("/sw.js", include_in_schema=False)
def service_worker():
    """Minimal service worker required for PWA installability."""
    return Response(
        content="self.addEventListener('fetch', () => {});",
        media_type="application/javascript",
        headers={"Service-Worker-Allowed": "/"},
    )


@app.get("/", include_in_schema=False)
def index():
    """Serve the React SPA or fall back to the legacy template."""
    # Prefer the React build if it exists
    dist_index = os.path.join(DIST_DIR, "index.html")
    if os.path.exists(dist_index):
        return FileResponse(dist_index, media_type="text/html")
    # Fall back to legacy Jinja2 template
    template_path = os.path.join(TEMPLATES_DIR, "dashboard.html")
    if os.path.exists(template_path):
        with open(template_path, encoding="utf-8") as f:
            html = f.read().replace("{{ version }}", __version__)
        return HTMLResponse(html)
    return HTMLResponse("<h1>Copilot Dashboard</h1><p>No frontend build found.</p>")


# Serve React build assets (JS, CSS, etc.) at root level so Vite's
# relative imports work (e.g. /assets/index-abc123.js)
if os.path.isdir(DIST_DIR):
    app.mount(
        "/assets", StaticFiles(directory=os.path.join(DIST_DIR, "assets")), name="dist-assets"
    )
