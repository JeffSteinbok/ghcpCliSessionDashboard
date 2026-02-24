"""
Copilot Dashboard - Flask web application.
Serves a real-time dashboard of all Copilot CLI sessions with:
  - Active vs Previous session split
  - Project-area grouping
  - Restart commands with copy buttons
  - Click-to-focus terminal windows
  - Light/dark mode and palette selector

Requires Python >= 3.12.
"""

import argparse
import json
import os
import sqlite3
import sys
from collections import Counter
from datetime import UTC, datetime

if sys.version_info < (3, 12):
    sys.exit("Error: Python >= 3.12 is required. Found: " + sys.version)

from flask import Flask, jsonify, render_template, request, send_from_directory

from .__version__ import __version__
from .process_tracker import (
    focus_session_window,
    get_recent_output,
    get_running_sessions,
    get_session_event_data,
)

app = Flask(__name__)

DB_PATH = os.path.join(os.path.expanduser("~"), ".copilot", "session-store.db")


def get_db():
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


def time_ago(iso_str):
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
        return iso_str


def get_group_name(session):
    """Derive a project/area group name from session metadata."""
    cwd = (session.get("cwd") or "").replace("\\", "/")
    summary = (session.get("summary") or "").lower()
    first_msg = (session.get("first_msg") or "").lower()
    last_cp = (session.get("last_cp_overview") or "").lower()
    context = f"{summary} {first_msg} {last_cp}"

    # --- CWD-based: extract project from path after /src/ ---
    if "/src/" in cwd.lower():
        idx = cwd.lower().index("/src/") + 5
        project = cwd[idx:].split("/")[0]
        if project:
            # Normalize known project families
            pl = project.lower()
            if "reviewstarclient" in pl:
                return "ReviewStarClient"
            if "repositorytools" in pl:
                return "OneDrive.RepositoryTools"
            return project

    # --- Content-based: look for project/repo references ---
    # Check for repo URLs or known project names in first message or checkpoints
    if "reviewstarclient" in context or "reviewstar" in context:
        return "ReviewStarClient"
    if "repositorytools" in context or "onedrive.repositorytools" in context:
        return "OneDrive.RepositoryTools"
    if "spo.core" in context or "spocore" in context:
        return "SPO.Core"

    # CWD subdirectory of user home
    if cwd:
        parts = cwd.replace("\\", "/").rstrip("/").split("/")
        meaningful = [
            p
            for p in parts
            if p.lower()
            not in (
                "",
                "c:",
                "q:",
                "d:",
                "users",
                "home",
                "jeffstei",
                "jeffsteinbok",
                "src",
            )
        ]
        if meaningful:
            return meaningful[-1]

    # --- Activity-based: infer from summary and first message ---
    cr_agent_terms = ["code review agent", "review framework", "review agent framework"]
    if any(w in context for w in cr_agent_terms):
        return "Code Review Agent Framework"
    if any(w in context for w in ["code review", "pr review", "merlinbot"]):
        return "PR Reviews"
    if "pipeline" in context or "build pipeline" in context or "ci/cd" in context:
        return "CI/CD Pipelines"
    if any(w in context for w in ["prune", "cleanup", "delete branch", "stale"]):
        return "Branch Cleanup"
    if any(w in context for w in ["sync", "merge", "rebase"]):
        return "Git Sync"
    if "dashboard" in context or "monitor" in context or "session" in context:
        return "Session Dashboard"
    if any(w in context for w in ["spec", "specification", "document"]):
        return "Specifications"

    return "General"


def get_recent_activity(session):
    """
    Get a short description of recent activity from the latest checkpoint,
    falling back to summary.
    """
    last_cp_title = session.get("last_cp_title") or ""
    last_cp_overview = session.get("last_cp_overview") or ""
    summary = session.get("summary") or ""

    if last_cp_title and last_cp_title.lower() != summary.lower():
        return last_cp_title
    if last_cp_overview:
        # Return first sentence
        first_sentence = last_cp_overview.split(". ")[0]
        if len(first_sentence) > 120:
            return first_sentence[:117] + "..."
        return first_sentence
    return ""


def _extract_extra_args(cmdline):
    """Extract extra CLI arguments from a copilot process command line.

    Returns the portion of the command line after the copilot executable,
    excluding --resume <sid> (which is always added separately).
    """
    if not cmdline:
        return ""
    # Find the copilot command portion (after the executable path)
    # cmdline looks like: "node /path/to/copilot --resume sid --yolo --model X"
    # or: "copilot --resume sid --yolo"
    import shlex
    try:
        parts = shlex.split(cmdline, posix=(os.name != "nt"))
    except ValueError:
        parts = cmdline.split()

    # Find the index of the copilot-like executable
    start = 0
    for i, p in enumerate(parts):
        if "copilot" in p.lower():
            start = i + 1
            break

    # Collect args, skipping --resume <sid>
    extra = []
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


def build_restart_command(session, yolo=False, cmdline=""):
    """Build a restart command for a session."""
    sid = session["id"]
    cwd = session.get("cwd") or ""
    parts = []
    if cwd:
        parts.append(f'cd "{cwd}" &&')
    cmd = f"copilot --resume {sid}"
    # Prefer extra args from the actual process command line
    extra = _extract_extra_args(cmdline)
    if extra:
        cmd += " " + extra
    elif yolo:
        cmd += " --yolo"
    parts.append(cmd)
    return " ".join(parts)


# ---------------------------------------------------------------------------
# API Routes
# ---------------------------------------------------------------------------


@app.route("/")
def index():
    return render_template("dashboard.html", version=__version__)


@app.route("/api/sessions")
def api_sessions():
    try:
        db = get_db()
    except FileNotFoundError as e:
        return jsonify({"error": str(e)}), 503
    rows = db.execute("""
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
    """).fetchall()
    db.close()

    # Get running processes to check yolo flag
    running = get_running_sessions()

    result = []
    for r in rows:
        s = dict(r)
        s["time_ago"] = time_ago(s["updated_at"])
        s["created_ago"] = time_ago(s["created_at"])
        proc = running.get(s["id"])
        is_running = proc is not None

        # Add running status and state to session
        s["is_running"] = is_running
        if proc:
            s["state"] = proc.get("state", "unknown")
            s["waiting_context"] = proc.get("waiting_context", "")
            s["bg_tasks"] = proc.get("bg_tasks", 0)
        else:
            s["state"] = None
            s["waiting_context"] = ""
            s["bg_tasks"] = 0

        # Get event data (cached for inactive sessions, fresh for active)
        evt = get_session_event_data(s["id"], is_running=is_running)

        # Backfill cwd/branch/repo from events when SQL has NULLs
        if not s.get("cwd") and evt.get("cwd"):
            s["cwd"] = evt["cwd"]
        if not s.get("branch") and evt.get("branch"):
            s["branch"] = evt["branch"]
        if not s.get("repository") and evt.get("repository"):
            s["repository"] = evt["repository"]

        s["group"] = get_group_name(s)
        s["recent_activity"] = get_recent_activity(s)
        had_yolo = proc["yolo"] if proc else False
        proc_cmdline = proc["cmdline"] if proc else ""
        s["restart_cmd"] = build_restart_command(s, yolo=had_yolo, cmdline=proc_cmdline)
        # MCP: from running process if active, else from cached event data
        if proc:
            s["mcp_servers"] = proc.get("mcp_servers", [])
        else:
            s["mcp_servers"] = evt.get("mcp_servers", [])
        # Tool call counts from cached event data
        s["tool_calls"] = evt.get("tool_calls", 0)
        s["subagent_runs"] = evt.get("subagent_runs", 0)
        # Current intent (most useful for active sessions)
        s["intent"] = evt.get("intent", "")
        # Don't send large text fields to the client
        s.pop("first_msg", None)
        s.pop("last_cp_overview", None)
        s.pop("last_cp_title", None)
        result.append(s)
    return jsonify(result)


@app.route("/api/session/<session_id>")
def api_session_detail(session_id):
    try:
        db = get_db()
    except FileNotFoundError as e:
        return jsonify({"error": str(e)}), 503
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
    events_dir = os.path.join(os.path.expanduser("~"), ".copilot", "session-state")
    events_file = os.path.join(events_dir, session_id, "events.jsonl")
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
    return jsonify(
        {
            "checkpoints": [dict(r) for r in checkpoints],
            "refs": [dict(r) for r in refs],
            "turns": [dict(r) for r in reversed(list(turns))],
            "recent_output": get_recent_output(session_id),
            "tool_counts": tool_counts,
            "files": [r["file_path"] for r in files],
        }
    )


@app.route("/api/files")
def api_files():
    """Return most-edited files across all sessions."""
    try:
        db = get_db()
    except FileNotFoundError as e:
        return jsonify({"error": str(e)}), 503
    rows = db.execute("""
        SELECT sf.file_path, COUNT(DISTINCT sf.session_id) as session_count,
        GROUP_CONCAT(DISTINCT sf.session_id) as session_ids
        FROM session_files sf GROUP BY sf.file_path
        ORDER BY session_count DESC LIMIT 100
    """).fetchall()
    db.close()
    return jsonify([dict(r) for r in rows])


@app.route("/api/processes")
def api_processes():
    """Return currently running copilot sessions mapped by session ID."""
    return jsonify(get_running_sessions())


@app.route("/api/focus/<session_id>", methods=["POST"])
def api_focus(session_id):
    """Focus the terminal window for a running session."""
    success, message = focus_session_window(session_id)
    return jsonify({"success": success, "message": message})


@app.route("/favicon.png")
def favicon():
    """Serve the Copilot favicon."""
    return send_from_directory(app.static_folder, "favicon.png", mimetype="image/png")


@app.route("/api/server-info")
def server_info():
    """Return server metadata including PID."""
    return jsonify({"pid": os.getpid(), "port": request.host.split(":")[-1]})


@app.route("/manifest.json")
def manifest():
    """PWA web app manifest — enables 'Install app' in Chrome/Edge."""
    data = {
        "name": "Copilot Dashboard",
        "short_name": "Copilot",
        "description": "Monitor all your GitHub Copilot CLI sessions in real-time.",
        "start_url": "/",
        "display": "standalone",
        "background_color": "#0d1117",
        "theme_color": "#0d1117",
        "icons": [
            {
                "src": "/favicon.png",
                "sizes": "64x64",
                "type": "image/png",
            },
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
    return jsonify(data)


@app.route("/sw.js")
def service_worker():
    """Minimal service worker required for PWA installability."""
    js = "self.addEventListener('fetch', () => {});"
    return (
        js,
        200,
        {"Content-Type": "application/javascript", "Service-Worker-Allowed": "/"},
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=5111)
    args = parser.parse_args()
    print("  Copilot Dashboard")
    print(f"  Reading from: {DB_PATH}")
    print(f"  Open http://localhost:{args.port}")
    app.run(host="127.0.0.1", port=args.port, debug=False)
