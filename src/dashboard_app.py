"""
Copilot Session Dashboard - Flask web application.
Serves a real-time dashboard of all Copilot CLI sessions with:
  - Active vs Previous session split
  - Project-area grouping
  - Restart commands with copy buttons
  - Click-to-focus terminal windows
  - Light/dark mode and palette selector

Requires Python >= 3.12.
"""

import sqlite3
import os
import sys
import argparse
from datetime import datetime, timezone

if sys.version_info < (3, 12):
    sys.exit("Error: Python >= 3.12 is required. Found: " + sys.version)

from flask import Flask, render_template_string, jsonify, request

from .process_tracker import (get_running_sessions, focus_session_window,
                              get_session_mcp_servers, get_recent_output,
                              get_session_tool_counts, get_session_event_data)
from .__version__ import __version__

app = Flask(__name__)

DB_PATH = os.path.join(os.path.expanduser("~"), ".copilot", "session-store.db")


def get_db():
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def time_ago(iso_str):
    if not iso_str:
        return "unknown"
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
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
        meaningful = [p for p in parts if p.lower() not in (
            "", "c:", "q:", "d:", "users", "home", "jeffstei", "jeffsteinbok", "src"
        )]
        if meaningful:
            return meaningful[-1]

    # --- Activity-based: infer from summary and first message ---
    if any(w in context for w in ["code review agent", "review framework", "review agent framework"]):
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


def build_restart_command(session, yolo=False):
    """Build a restart command for a session."""
    sid = session["id"]
    cwd = session.get("cwd") or ""
    parts = []
    if cwd:
        parts.append(f'cd "{cwd}" &&')
    cmd = f"copilot --resume {sid}"
    if yolo:
        cmd += " --yolo"
    parts.append(cmd)
    return " ".join(parts)


# ---------------------------------------------------------------------------
# HTML Template
# ---------------------------------------------------------------------------

TEMPLATE = r"""
<!DOCTYPE html>
<html lang="en" data-mode="dark" data-palette="default">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Copilot Session Dashboard</title>
<link rel="icon" href="/favicon.svg" type="image/svg+xml">
<style>
  /* ===== THEME SYSTEM ===== */
  /* Default Dark */
  [data-mode="dark"][data-palette="default"] {
    --bg: #0d1117; --surface: #161b22; --surface2: #21262d;
    --border: #30363d; --text: #e6edf3; --text2: #8b949e;
    --accent: #58a6ff; --green: #3fb950; --yellow: #d29922;
    --red: #f85149; --purple: #bc8cff;
    --group-bg: #0d1117; --group-border: #21262d;
    --copy-bg: #21262d; --copy-hover: #30363d;
    --modal-overlay: rgba(0,0,0,0.7);
  }
  /* Default Light */
  [data-mode="light"][data-palette="default"] {
    --bg: #ffffff; --surface: #f6f8fa; --surface2: #eaeef2;
    --border: #d0d7de; --text: #1f2328; --text2: #656d76;
    --accent: #0969da; --green: #1a7f37; --yellow: #9a6700;
    --red: #cf222e; --purple: #8250df;
    --group-bg: #f6f8fa; --group-border: #d0d7de;
    --copy-bg: #eaeef2; --copy-hover: #d0d7de;
    --modal-overlay: rgba(0,0,0,0.4);
  }
  /* Pink Dark */
  [data-mode="dark"][data-palette="pink"] {
    --bg: #1a0a14; --surface: #2d1225; --surface2: #3d1a33;
    --border: #5c2d4a; --text: #f5dce8; --text2: #b8849e;
    --accent: #ff6eb4; --green: #5cdb95; --yellow: #ffd166;
    --red: #ff4d6d; --purple: #e0aaff;
    --group-bg: #1a0a14; --group-border: #3d1a33;
    --copy-bg: #3d1a33; --copy-hover: #5c2d4a;
    --modal-overlay: rgba(20,5,15,0.8);
  }
  /* Pink Light */
  [data-mode="light"][data-palette="pink"] {
    --bg: #fff5f9; --surface: #fce4ec; --surface2: #f8bbd0;
    --border: #f48fb1; --text: #4a0e2b; --text2: #8c4566;
    --accent: #d81b78; --green: #2e7d57; --yellow: #c77600;
    --red: #c62048; --purple: #9c27b0;
    --group-bg: #fff0f5; --group-border: #f48fb1;
    --copy-bg: #f8bbd0; --copy-hover: #f48fb1;
    --modal-overlay: rgba(74,14,43,0.3);
  }

  /* ===== BASE ===== */
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;
    background: var(--bg); color: var(--text); line-height: 1.6;
    transition: background 0.2s, color 0.2s; font-size: 15px;
  }
  a { color: var(--accent); text-decoration: none; }
  a:hover { text-decoration: underline; }

  /* ===== HEADER ===== */
  .header {
    background: var(--surface); border-bottom: 1px solid var(--border);
    padding: 12px 24px; display: flex; align-items: center; gap: 14px;
    position: sticky; top: 0; z-index: 100; flex-wrap: wrap;
  }
  .header .logo { font-size: 22px; }
  .header h1 { font-size: 22px; font-weight: 600; white-space: nowrap; }
  .header-credits { font-size: 13px; color: var(--text2); white-space: nowrap; }
  .header-credits a { color: var(--accent); cursor: pointer; }
  .header-right { margin-left: auto; display: flex; align-items: center; gap: 12px; }
  .theme-controls { display: flex; align-items: center; gap: 8px; }
  .theme-btn, .palette-select {
    background: var(--surface2); border: 1px solid var(--border); color: var(--text);
    border-radius: 6px; padding: 5px 12px; font-size: 14px; cursor: pointer;
    transition: background 0.15s;
  }
  .theme-btn:hover, .palette-select:hover { background: var(--copy-hover); }
  .header-meta { color: var(--text2); font-size: 13px; white-space: nowrap; }
  .refresh-dot {
    display: inline-block; width: 7px; height: 7px; border-radius: 50%;
    background: var(--green); margin-right: 4px; animation: pulse 2s infinite;
  }
  @keyframes pulse { 0%,100%{opacity:1;} 50%{opacity:0.3;} }

  /* ===== CONTAINER ===== */
  .container { max-width: 1280px; margin: 0 auto; padding: 20px 24px; }

  /* ===== STATS ===== */
  .stats-row {
    display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
    gap: 10px; margin-bottom: 20px;
  }
  .stat-card {
    background: var(--surface); border: 1px solid var(--border); border-radius: 8px;
    padding: 14px; text-align: center;
  }
  .stat-card .num { font-size: 30px; font-weight: 700; color: var(--accent); }
  .stat-card .label { font-size: 13px; color: var(--text2); text-transform: uppercase; letter-spacing: 0.5px; }

  /* ===== TABS ===== */
  .tabs { display: flex; gap: 0; margin-bottom: 16px; border-bottom: 2px solid var(--border); }
  .tab {
    padding: 10px 22px; font-size: 16px; font-weight: 500; cursor: pointer;
    color: var(--text2); border-bottom: 2px solid transparent; margin-bottom: -2px;
    transition: color 0.15s, border-color 0.15s;
  }
  .tab:hover { color: var(--text); }
  .tab.active { color: var(--accent); border-bottom-color: var(--accent); }
  .tab .count {
    background: var(--surface2); border-radius: 10px; padding: 2px 8px;
    font-size: 13px; margin-left: 6px;
  }
  .tab.active .count { background: rgba(88,166,255,0.15); color: var(--accent); }

  /* ===== SEARCH ===== */
  .search-bar {
    width: 100%; padding: 11px 16px; background: var(--surface); border: 1px solid var(--border);
    border-radius: 8px; color: var(--text); font-size: 15px; margin-bottom: 16px; outline: none;
  }
  .search-bar:focus { border-color: var(--accent); }
  .search-bar::placeholder { color: var(--text2); }

  /* ===== GROUPS ===== */
  .group {
    margin-bottom: 20px; border: 1px solid var(--group-border);
    border-radius: 10px; overflow: hidden;
  }
  .group-header {
    background: var(--surface); padding: 12px 18px; font-weight: 600; font-size: 16px;
    display: flex; align-items: center; gap: 8px;
    border-bottom: 1px solid var(--group-border); cursor: pointer; user-select: none;
  }
  .group-header .arrow { transition: transform 0.2s; font-size: 10px; color: var(--text2); }
  .group-header.collapsed .arrow { transform: rotate(-90deg); }
  .group-header .group-count { font-size: 13px; color: var(--text2); font-weight: 400; }
  .group-body { display: flex; flex-direction: column; }
  .group-header.collapsed + .group-body { display: none; }

  /* ===== SESSION CARD ===== */
  .session-card {
    background: var(--surface); border-bottom: 1px solid var(--border);
    padding: 14px 16px; transition: background 0.1s;
  }
  .session-card:last-child { border-bottom: none; }
  .session-card:hover { background: var(--surface2); }
  .session-card.active-session { border-left: 3px solid var(--green); }
  .session-card.waiting-session { border-left: 3px solid var(--yellow); }
  .session-card.idle-session { border-left: 3px solid var(--accent); }
  .session-top { display: flex; align-items: flex-start; gap: 10px; cursor: pointer; }
  .session-title { font-weight: 600; font-size: 16px; flex: 1; }
  .session-time { color: var(--text2); font-size: 13px; white-space: nowrap; }
  .live-dot {
    width: 8px; height: 8px; border-radius: 50%; background: var(--green);
    animation: pulse 1.5s infinite; flex-shrink: 0; margin-top: 7px;
  }
  .live-dot.waiting { background: var(--yellow); animation: none; }
  .live-dot.idle { background: var(--accent); animation: none; }
  .session-meta { display: flex; gap: 8px; margin-top: 6px; flex-wrap: wrap; align-items: center; }
  .badge {
    font-size: 12px; padding: 2px 9px; border-radius: 10px; font-weight: 500;
  }
  .badge-repo { background: rgba(88,166,255,0.12); color: var(--accent); }
  .badge-branch { background: rgba(188,140,255,0.12); color: var(--purple); }
  .badge-turns { background: rgba(63,185,80,0.12); color: var(--green); }
  .badge-files { background: rgba(210,153,34,0.12); color: var(--yellow); }
  .badge-cp { background: rgba(248,81,73,0.12); color: var(--red); }
  .badge-active { background: rgba(63,185,80,0.2); color: var(--green); font-weight: 600; }
  .badge-waiting { background: rgba(210,153,34,0.2); color: var(--yellow); font-weight: 600; }
  .badge-working { background: rgba(63,185,80,0.2); color: var(--green); font-weight: 600; }
  .badge-thinking { background: rgba(63,185,80,0.2); color: var(--green); font-weight: 600; }
  .badge-idle { background: rgba(88,166,255,0.2); color: var(--accent); font-weight: 600; }
  .badge-yolo { background: rgba(248,81,73,0.15); color: var(--red); }
  .badge-mcp { background: rgba(188,140,255,0.15); color: var(--purple); }
  .badge-bg { background: rgba(210,153,34,0.15); color: var(--yellow); }
  .badge-focus { cursor: pointer; background: rgba(88,166,255,0.15); color: var(--accent); }
  .badge-focus:hover { background: rgba(88,166,255,0.3); }
  .cwd-text {
    font-family: 'Cascadia Code','Fira Code',monospace; font-size: 13px;
    color: var(--text2); margin-top: 4px;
  }

  /* ===== RESTART COMMAND ===== */
  .restart-row {
    display: flex; align-items: center; gap: 8px; margin-top: 8px;
    background: var(--copy-bg); border-radius: 6px; padding: 8px 12px;
    font-family: 'Cascadia Code','Fira Code',monospace; font-size: 13px;
    color: var(--text2); overflow-x: auto;
  }
  .restart-cmd { flex: 1; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .copy-btn, .focus-btn {
    background: var(--surface); border: 1px solid var(--border); color: var(--text2);
    border-radius: 4px; padding: 5px 10px; font-size: 13px; cursor: pointer;
    white-space: nowrap; transition: background 0.15s, color 0.15s; flex-shrink: 0;
  }
  .copy-btn:hover, .focus-btn:hover { background: var(--accent); color: #fff; border-color: var(--accent); }
  .copy-btn.copied { background: var(--green); color: #fff; border-color: var(--green); }

  /* ===== DETAIL PANEL ===== */
  .session-detail { display: none; margin-top: 12px; border-top: 1px solid var(--border); padding-top: 12px; }
  .session-card.expanded .session-detail { display: block; }
  .detail-section { margin-bottom: 14px; }
  .detail-section h3 {
    font-size: 14px; color: var(--text2); text-transform: uppercase;
    letter-spacing: 0.5px; margin-bottom: 8px;
  }
  .checkpoint {
    background: var(--surface2); border-radius: 6px; padding: 10px; margin-bottom: 6px;
    border-left: 3px solid var(--accent);
  }
  .checkpoint .cp-title { font-weight: 600; font-size: 15px; }
  .checkpoint .cp-body { color: var(--text2); font-size: 14px; margin-top: 3px; }
  .turn-item { padding: 8px 0; border-bottom: 1px solid var(--border); font-size: 14px; }
  .turn-item:last-child { border-bottom: none; }
  .turn-user { color: var(--accent); font-weight: 500; }
  .turn-assistant { color: var(--text2); }
  .file-list { display: flex; flex-wrap: wrap; gap: 4px; }
  .file-tag {
    font-size: 12px; background: var(--surface2); border: 1px solid var(--border);
    border-radius: 3px; padding: 2px 8px; font-family: 'Cascadia Code','Fira Code',monospace;
  }
  .ref-tag {
    font-size: 12px; background: rgba(63,185,80,0.1); border: 1px solid rgba(63,185,80,0.3);
    border-radius: 3px; padding: 2px 8px; color: var(--green);
  }
  .empty { color: var(--text2); font-style: italic; font-size: 14px; padding: 12px 0; }
  .loading { text-align: center; padding: 30px; color: var(--text2); }

  /* ===== MODAL ===== */
  .modal-overlay {
    display: none; position: fixed; inset: 0; background: var(--modal-overlay);
    z-index: 200; align-items: center; justify-content: center;
  }
  .modal-overlay.open { display: flex; }
  .modal {
    background: var(--surface); border: 1px solid var(--border); border-radius: 12px;
    padding: 28px; max-width: 900px; width: 90%; max-height: 80vh; overflow-y: auto;
    box-shadow: 0 16px 48px rgba(0,0,0,0.3);
  }
  .modal h2 { font-size: 20px; margin-bottom: 14px; }
  .modal p { color: var(--text2); font-size: 15px; line-height: 1.7; margin-bottom: 10px; }
  .modal ul { color: var(--text2); font-size: 15px; line-height: 1.7; margin-left: 18px; margin-bottom: 10px; }
  .modal .close-btn {
    background: var(--accent); color: #fff; border: none; border-radius: 6px;
    padding: 8px 20px; cursor: pointer; font-size: 13px; margin-top: 8px;
  }
  .tab-panel { display: none; }
  .tab-panel.active { display: block; }

  /* Scrollbar styling */
  ::-webkit-scrollbar { width: 6px; }
  ::-webkit-scrollbar-track { background: var(--bg); }
  ::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }

  /* ===== TILE VIEW ===== */
  .tile-grid {
    display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
    gap: 12px;
  }
  .tile-card {
    background: var(--surface); border: 1px solid var(--border); border-radius: 10px;
    padding: 14px; cursor: pointer; transition: border-color 0.15s, background 0.15s;
    display: flex; flex-direction: column; gap: 6px; min-height: 100px;
  }
  .tile-card:hover { border-color: var(--accent); background: var(--surface2); }
  .tile-card.active-tile { border-left: 4px solid var(--green); }
  .tile-card.waiting-tile { border-left: 4px solid var(--yellow); }
  .tile-card.idle-tile { border-left: 4px solid var(--accent); }
  .tile-top { display: flex; align-items: baseline; gap: 8px; }
  .tile-top .live-dot { position: relative; top: -1px; }
  .tile-title { font-weight: 600; font-size: 14px; flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .tile-time { font-size: 11px; color: var(--text2); white-space: nowrap; }
  .tile-subtitle { font-size: 12px; color: var(--text2); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .tile-meta { display: flex; gap: 6px; flex-wrap: wrap; align-items: center; }
  .tile-group-header {
    grid-column: 1 / -1; font-weight: 600; font-size: 15px; color: var(--text2);
    padding: 8px 0 2px 0; border-bottom: 1px solid var(--border); margin-top: 4px;
  }

  /* ===== VIEW TOGGLE ===== */
  .view-toggle { display: flex; gap: 4px; }
  .view-btn {
    background: var(--surface2); border: 1px solid var(--border); color: var(--text2);
    border-radius: 6px; padding: 5px 12px; font-size: 14px; cursor: pointer;
    transition: background 0.15s, color 0.15s;
  }
  .view-btn:hover { background: var(--copy-hover); }
  .view-btn.active { background: var(--accent); color: #fff; border-color: var(--accent); }

  /* ===== DETAIL MODAL ===== */
  .detail-modal-overlay {
    display: none; position: fixed; inset: 0; background: var(--modal-overlay);
    z-index: 200; align-items: flex-start; justify-content: center; padding-top: 60px;
  }
  .detail-modal-overlay.open { display: flex; }
  .detail-modal {
    background: var(--surface); border: 1px solid var(--border); border-radius: 12px;
    padding: 24px; max-width: 700px; width: 95%; max-height: 80vh; overflow-y: auto;
    box-shadow: 0 16px 48px rgba(0,0,0,0.3);
  }
  .detail-modal-header { display: flex; align-items: center; gap: 10px; margin-bottom: 16px; }
  .detail-modal-header h2 { font-size: 18px; flex: 1; }
  .detail-modal-header .close-x {
    background: none; border: none; color: var(--text2); font-size: 22px;
    cursor: pointer; padding: 4px 8px; border-radius: 4px;
  }
  .detail-modal-header .close-x:hover { background: var(--surface2); color: var(--text); }
</style>
</head>
<body>

<!-- ===== HEADER ===== -->
<div class="header">
  <span class="logo">&#x1F916;</span>
  <h1>Copilot Session Dashboard</h1>
  <div class="header-credits">
    Created by <strong>JeffStei</strong>
    &nbsp;&bull;&nbsp; v{{ version }}
    &nbsp;&bull;&nbsp;
    <a onclick="document.getElementById('help-modal').classList.add('open')">What is this?</a>
  </div>
  <div class="header-right">
    <div class="theme-controls">
      <button class="theme-btn" id="mode-toggle" title="Toggle light/dark mode">&#x1F319; Dark</button>
      <select class="palette-select" id="palette-select" title="Color palette">
        <option value="default">&#x1F308; Default</option>
        <option value="pink">&#x1F338; Pink</option>
      </select>
    </div>
    <div class="header-meta">
      <span class="refresh-dot"></span>
      <span id="last-updated">-</span>
    </div>
  </div>
</div>

<!-- ===== HELP MODAL ===== -->
<div class="modal-overlay" id="help-modal" onclick="if(event.target===this)this.classList.remove('open')">
  <div class="modal">
    <h2>&#x1F916; Copilot Session Dashboard</h2>
    <p>A local dashboard that monitors all your GitHub Copilot CLI sessions in real-time.</p>
    <p><a href="https://github.com/JeffSteinbok/ghcpCliSessionDashboard" target="_blank" style="color:var(--accent);text-decoration:underline">&#x1F4D6; View full documentation on GitHub</a></p>
    <p><strong>Features:</strong></p>
    <ul>
      <li><strong>Active vs Previous</strong> &mdash; sessions with a running process show in the Active tab with a live indicator; completed sessions are in Previous.</li>
      <li><strong>Session states</strong> &mdash; <span style="color:var(--green)">&#x25CF; Working/Thinking</span> (actively running), <span style="color:var(--yellow)">&#x25CF; Waiting</span> (needs your input), <span style="color:var(--accent)">&#x25CF; Idle</span> (done, ready for next task).</li>
      <li><strong>Desktop notifications</strong> &mdash; click the &#x1F515; button to enable browser notifications. You'll get an alert whenever a session transitions from working to waiting or idle, so you can stay on top of sessions that need attention.</li>
      <li><strong>Background tasks</strong> &mdash; sessions running subagents show a badge with the count of active background tasks.</li>
      <li><strong>Grouped by project</strong> &mdash; sessions are automatically categorized by repository or working directory.</li>
      <li><strong>Restart commands</strong> &mdash; each session has a copy-pasteable <code>copilot</code> command to resume it.</li>
      <li><strong>Focus window</strong> &mdash; click the &#x1F4FA; button on an active session to bring its terminal to the foreground.</li>
      <li><strong>Tile &amp; List views</strong> &mdash; tile view for at-a-glance status, list view for full details. Click any tile/row to expand.</li>
      <li><strong>Themes</strong> &mdash; toggle light/dark mode and switch color palettes using the controls in the header.</li>
    </ul>
    <p><strong>Refresh rates:</strong> Active sessions refresh every 5 seconds. Previous sessions refresh every 30 seconds.</p>
    <p><strong>Slash commands:</strong></p>
    <ul>
      <li><code>/dashboard install</code> &mdash; install prerequisites</li>
      <li><code>/dashboard start</code> &mdash; start the dashboard</li>
      <li><code>/dashboard stop</code> &mdash; stop the dashboard</li>
      <li><code>/dashboard status</code> &mdash; check if running</li>
    </ul>
    <button class="close-btn" onclick="document.getElementById('help-modal').classList.remove('open')">Got it</button>
  </div>
</div>

<!-- ===== DETAIL MODAL (for tile view) ===== -->
<div class="detail-modal-overlay" id="detail-modal" onclick="if(event.target===this)closeDetailModal()">
  <div class="detail-modal">
    <div class="detail-modal-header">
      <h2 id="detail-modal-title"></h2>
      <button class="close-x" onclick="closeDetailModal()">&#x2715;</button>
    </div>
    <div id="detail-modal-body"></div>
  </div>
</div>

<!-- ===== MAIN CONTENT ===== -->
<div class="container">
  <div class="stats-row" id="stats-row"></div>

  <div style="display:flex;align-items:center;gap:12px;margin-bottom:16px">
    <div class="tabs" style="margin-bottom:0;flex:1">
      <div class="tab active" data-tab="active" onclick="switchTab('active')">
        &#x26A1; Active <span class="count" id="active-count">0</span>
      </div>
      <div class="tab" data-tab="previous" onclick="switchTab('previous')">
        &#x1F4CB; Previous <span class="count" id="previous-count">0</span>
      </div>
    </div>
    <div class="view-toggle">
      <button class="view-btn" id="notif-btn" onclick="enableNotifications()" title="Enable desktop notifications">&#x1F515; Notifications Off</button>
      <button class="view-btn active" id="view-tile" onclick="setView('tile')" title="Tile view">&#x25A6;</button>
      <button class="view-btn" id="view-list" onclick="setView('list')" title="List view">&#x2630;</button>
    </div>
  </div>

  <input class="search-bar" id="search" type="text"
         placeholder="&#x1F50D;  Filter sessions by name, repo, branch, MCP server, or directory...">

  <div class="tab-panel active" id="panel-active">
    <div class="loading" id="active-loading">Loading active sessions...</div>
  </div>
  <div class="tab-panel" id="panel-previous">
    <div class="loading" id="previous-loading">Loading sessions...</div>
  </div>
</div>

<script>
// ===== STATE =====
let allSessions = [];
let runningPids = {};  // {session_id: process_info}
let currentTab = 'active';
let activeTimer = null;
let previousTimer = null;
let expandedSessionIds = new Set();  // persist across re-renders
let collapsedGroups = new Set();     // persist across re-renders
let loadedDetails = {};              // cache detail HTML by session id
let currentView = localStorage.getItem('dash-view') || 'tile';

// ===== VIEW TOGGLE =====
function setView(view) {
  currentView = view;
  localStorage.setItem('dash-view', view);
  document.getElementById('view-list').classList.toggle('active', view === 'list');
  document.getElementById('view-tile').classList.toggle('active', view === 'tile');
  render();
}
function initView() {
  document.getElementById('view-list').classList.toggle('active', currentView === 'list');
  document.getElementById('view-tile').classList.toggle('active', currentView === 'tile');
}

// ===== THEME =====
function applyTheme() {
  const mode = localStorage.getItem('dash-mode') || 'dark';
  const palette = localStorage.getItem('dash-palette') || 'default';
  document.documentElement.setAttribute('data-mode', mode);
  document.documentElement.setAttribute('data-palette', palette);
  document.getElementById('mode-toggle').innerHTML = mode === 'dark' ? '&#x1F319; Dark' : '&#x2600;&#xFE0F; Light';
  document.getElementById('palette-select').value = palette;
}
document.getElementById('mode-toggle').onclick = () => {
  const cur = localStorage.getItem('dash-mode') || 'dark';
  localStorage.setItem('dash-mode', cur === 'dark' ? 'light' : 'dark');
  applyTheme();
};
document.getElementById('palette-select').onchange = (e) => {
  localStorage.setItem('dash-palette', e.target.value);
  applyTheme();
};
applyTheme();

// ===== TABS =====
function switchTab(tab) {
  currentTab = tab;
  document.querySelectorAll('.tab').forEach(t => t.classList.toggle('active', t.dataset.tab === tab));
  document.querySelectorAll('.tab-panel').forEach(p => p.classList.toggle('active', p.id === 'panel-' + tab));
}

// ===== DATA FETCH =====
async function fetchSessions() {
  try {
    const [sessResp, procResp] = await Promise.all([
      fetch('/api/sessions'), fetch('/api/processes')
    ]);
    allSessions = await sessResp.json();
    runningPids = await procResp.json();
  } catch(e) { console.error('Fetch error:', e); }
  render();
  document.getElementById('last-updated').textContent = new Date().toLocaleTimeString();
}

async function fetchProcesses() {
  try {
    const resp = await fetch('/api/processes');
    const newPids = await resp.json();
    checkForWaitingTransitions(runningPids, newPids);
    runningPids = newPids;
  } catch(e) {}
  render();
}

// ===== DESKTOP NOTIFICATIONS =====
let notificationsEnabled = false;
function enableNotifications() {
  if (!('Notification' in window)) { alert('Desktop notifications not supported in this browser'); return; }
  if (Notification.permission === 'granted') {
    notificationsEnabled = !notificationsEnabled; // toggle
    updateNotifBtn();
    if (notificationsEnabled) {
      new Notification('Copilot Dashboard', { body: 'Notifications enabled! You will be alerted when a session needs input.' });
    }
    return;
  }
  if (Notification.permission === 'denied') {
    alert('Notifications are blocked.\n\nTo enable in Edge:\n1. Click the lock icon in the address bar\n2. Click "Permissions for this site"\n3. Set Notifications to "Allow"\n4. Refresh this page and click the button again');
    return;
  }
  // default — ask permission (requires user gesture, which this click provides)
  Notification.requestPermission().then(p => {
    notificationsEnabled = (p === 'granted');
    updateNotifBtn();
    if (notificationsEnabled) {
      new Notification('Copilot Dashboard', { body: 'Notifications enabled! You will be alerted when a session needs input.' });
    } else {
      alert('Notification permission was not granted.');
    }
  });
}
function updateNotifBtn() {
  const btn = document.getElementById('notif-btn');
  if (!btn) return;
  if (notificationsEnabled) {
    btn.innerHTML = '&#x1F514; Notifications On';
    btn.style.opacity = '1';
  } else {
    btn.innerHTML = '&#x1F515; Notifications Off';
    btn.style.opacity = '0.6';
  }
}
// Auto-enable if already granted (no gesture needed)
if (typeof Notification !== 'undefined' && Notification.permission === 'granted') {
  notificationsEnabled = true;
}

function checkForWaitingTransitions(oldPids, newPids) {
  if (!notificationsEnabled) return;
  for (const [sid, info] of Object.entries(newPids)) {
    const oldState = oldPids[sid] ? oldPids[sid].state : null;
    if (!oldState) continue; // skip first poll (no previous state)
    // Notify when state changes to something that needs attention
    if (info.state !== oldState && (info.state === 'waiting' || info.state === 'idle')) {
      const session = allSessions.find(s => s.id === sid);
      const title = session ? (session.intent || session.summary || 'Copilot Session') : 'Copilot Session';
      const body = info.waiting_context || (info.state === 'waiting' ? 'Session is waiting for your input' : 'Session is done and ready for next task');
      new Notification(title, { body: body, tag: 'copilot-' + sid });
    }
  }
}
// ===== RENDER =====
function render() {
  const filter = (document.getElementById('search').value || '').toLowerCase();

  // Split active vs previous
  const active = [], previous = [];
  allSessions.forEach(s => {
    const hay = [s.summary, s.repository, s.branch, s.cwd, s.group, s.intent, ...(s.mcp_servers || [])].filter(Boolean).join(' ').toLowerCase();
    if (filter && !hay.includes(filter)) return;
    if (runningPids[s.id]) { active.push(s); } else { previous.push(s); }
  });

  document.getElementById('active-count').textContent = active.length;
  document.getElementById('previous-count').textContent = previous.length;
  renderStats(active, previous);
  if (currentView === 'tile') {
    renderTilePanel('panel-active', active, true);
    renderTilePanel('panel-previous', previous, false);
  } else {
    renderPanel('panel-active', active, true);
    renderPanel('panel-previous', previous, false);
  }
}

function renderStats(active, previous) {
  const total = allSessions.length;
  const totalTurns = allSessions.reduce((a, s) => a + (s.turn_count || 0), 0);
  const totalToolCalls = allSessions.reduce((a, s) => a + (s.tool_calls || 0), 0);
  const totalSubagents = allSessions.reduce((a, s) => a + (s.subagent_runs || 0), 0);
  document.getElementById('stats-row').innerHTML = `
    <div class="stat-card"><div class="num">${active.length}</div><div class="label">Active Now</div></div>
    <div class="stat-card"><div class="num">${total}</div><div class="label">Total Sessions</div></div>
    <div class="stat-card"><div class="num">${totalTurns.toLocaleString()}</div><div class="label">Conversations</div></div>
    <div class="stat-card"><div class="num">${totalToolCalls.toLocaleString()}</div><div class="label">Tool Calls</div></div>
    <div class="stat-card"><div class="num">${totalSubagents.toLocaleString()}</div><div class="label">Sub-agents</div></div>
  `;
}

function renderPanel(panelId, sessions, isActive) {
  const panel = document.getElementById(panelId);
  if (!sessions.length) {
    panel.innerHTML = `<div class="empty">${isActive ? 'No active sessions detected.' : 'No previous sessions.'}</div>`;
    return;
  }

  // Group sessions
  const groups = {};
  sessions.forEach(s => {
    const g = s.group || 'General';
    (groups[g] = groups[g] || []).push(s);
  });

  // Sort groups: most sessions first
  const sortedGroups = Object.entries(groups).sort((a,b) => b[1].length - a[1].length);

  let html = '';
  for (const [groupName, items] of sortedGroups) {
    const gid = (panelId + '-' + groupName).replace(/[^a-zA-Z0-9]/g, '_');
    const isCollapsed = collapsedGroups.has(gid);
    html += `<div class="group">
      <div class="group-header ${isCollapsed ? 'collapsed' : ''}" onclick="toggleGroup(this, '${gid}')">
        <span class="arrow">&#x25BC;</span>
        ${esc(groupName)}
        <span class="group-count">(${items.length})</span>
      </div>
      <div class="group-body">`;

    for (const s of items) {
      const isRunning = !!runningPids[s.id];
      const pinfo = isRunning ? (runningPids[s.id] || {}) : {};
      const isWaiting = isRunning && pinfo.state === 'waiting';
      const isIdle = isRunning && pinfo.state === 'idle';
      const cardClass = isRunning ? (isWaiting ? 'waiting-session' : (isIdle ? 'idle-session' : 'active-session')) : '';
      const isExpanded = expandedSessionIds.has(s.id);
      const state = isRunning ? (pinfo.state || 'unknown') : '';
      const waitCtx = isRunning ? (pinfo.waiting_context || '') : '';
      const stateIcons = { waiting: '&#x23F3; Waiting', working: '&#x2692;&#xFE0F; Working', thinking: '&#x1F914; Thinking', idle: '&#x1F535; Idle', unknown: '&#x2753; Unknown' };
      const stateCls = { waiting: 'badge-waiting', working: 'badge-working', thinking: 'badge-thinking', idle: 'badge-idle', unknown: 'badge-active' };

      html += `
        <div class="session-card ${cardClass} ${isExpanded ? 'expanded' : ''}" data-id="${s.id}">
          <div style="display:flex;gap:10px">
            <div style="flex:1;min-width:0" onclick="toggleDetail('${s.id}')" style="cursor:pointer">
              <div class="session-top" onclick="toggleDetail('${s.id}')">
                ${isRunning ? `<span class="live-dot ${isWaiting ? 'waiting' : (isIdle ? 'idle' : '')}" title="${isWaiting ? 'Waiting for input' : (isIdle ? 'Idle' : 'Running')}"></span>` : ''}
                <div class="session-title">${isRunning && s.intent ? '&#x1F916; ' + esc(s.intent) : esc(s.summary || '(Untitled session)')}</div>
              </div>
              ${isRunning && s.intent ? `<div class="cwd-text" style="opacity:0.7">${esc(s.summary || '')}</div>` : ''}
              ${s.cwd ? `<div class="cwd-text">&#x1F4C1; ${esc(s.cwd)}</div>` : ''}
              ${s.recent_activity ? `<div class="cwd-text" style="color:var(--accent)">&#x1F4DD; ${esc(s.recent_activity)}</div>` : ''}
              ${isWaiting && waitCtx ? `<div class="cwd-text" style="color:var(--yellow)">&#x23F3; ${esc(waitCtx)}</div>` : ''}
              ${isIdle && waitCtx ? `<div class="cwd-text" style="color:var(--accent)">&#x1F535; ${esc(waitCtx)}</div>` : ''}
              <div class="session-meta">
                ${isRunning && state ? `<span class="badge ${stateCls[state] || 'badge-active'}">${stateIcons[state] || state}</span>` : ''}
                ${isRunning && pinfo.bg_tasks ? `<span class="badge badge-bg">&#x2699;&#xFE0F; ${pinfo.bg_tasks} bg task${pinfo.bg_tasks > 1 ? 's' : ''}</span>` : ''}
                ${s.branch ? `<span class="badge badge-branch">&#x1F33F; ${esc(s.branch)}</span>` : ''}
                <span class="badge badge-turns">&#x1F4AC; ${s.turn_count} turns</span>
                ${s.checkpoint_count ? `<span class="badge badge-cp">&#x1F3C1; ${s.checkpoint_count} checkpoints</span>` : ''}
                ${s.mcp_servers && s.mcp_servers.length ? s.mcp_servers.map(m => `<span class="badge badge-mcp">&#x1F50C; ${esc(m)}</span>`).join('') : ''}
              </div>
            </div>
            <div style="flex-shrink:0;text-align:right">
              <div class="session-time" title="${esc(s.updated_at)}">started ${esc(s.created_ago)}</div>
              ${isRunning && pinfo.yolo ? `<div style="margin-top:4px"><span class="badge badge-yolo">&#x1F525; YOLO</span></div>` : ''}
            </div>
          </div>`;

      html += `
          <div class="restart-row">
            <span class="restart-cmd" title="${esc(s.restart_cmd)}">${esc(s.restart_cmd)}</span>
            <button class="copy-btn" onclick="copyCmd(this, '${esc(s.restart_cmd)}')">&#x1F4CB; Copy</button>
            ${isRunning ? `<button class="focus-btn" onclick="focusSession('${s.id}')">&#x1F4FA; Focus</button>` : ''}
          </div>
          <div class="session-detail" id="detail-${s.id}"></div>
        </div>`;
    }
    html += '</div></div>';
  }
  panel.innerHTML = html;

  // Restore cached detail HTML for expanded sessions
  expandedSessionIds.forEach(id => {
    const detail = document.getElementById('detail-' + id);
    if (detail && loadedDetails[id]) {
      detail.innerHTML = loadedDetails[id];
    } else if (detail && expandedSessionIds.has(id)) {
      // Re-fetch if no cache
      loadDetail(id);
    }
  });
}

function toggleGroup(el, gid) {
  el.classList.toggle('collapsed');
  if (el.classList.contains('collapsed')) {
    collapsedGroups.add(gid);
  } else {
    collapsedGroups.delete(gid);
  }
}

// ===== INTERACTIONS =====
async function toggleDetail(id) {
  const card = document.querySelector(`.session-card[data-id="${id}"]`);
  if (!card) return;
  const wasExpanded = card.classList.contains('expanded');

  // Collapse all in same panel, update tracking
  card.closest('.tab-panel').querySelectorAll('.session-card.expanded').forEach(c => {
    c.classList.remove('expanded');
    expandedSessionIds.delete(c.dataset.id);
  });
  if (wasExpanded) return;

  card.classList.add('expanded');
  expandedSessionIds.add(id);
  await loadDetail(id);
}

async function loadDetail(id) {
  const detail = document.getElementById('detail-' + id);
  if (!detail) return;
  detail.innerHTML = '<div class="loading">Loading...</div>';

  try {
    const resp = await fetch('/api/session/' + id);
    const data = await resp.json();
    let html = '';

    if (data.checkpoints && data.checkpoints.length) {
      html += '<div class="detail-section"><h3>&#x1F3C1; Checkpoints</h3>';
      data.checkpoints.forEach(cp => {
        html += `<div class="checkpoint">
          <div class="cp-title">#${cp.checkpoint_number}: ${esc(cp.title || 'Checkpoint')}</div>
          ${cp.overview ? `<div class="cp-body">${esc(cp.overview)}</div>` : ''}
          ${cp.next_steps ? `<div class="cp-body" style="margin-top:4px;color:var(--yellow)"><strong>Next:</strong> ${esc(cp.next_steps)}</div>` : ''}
        </div>`;
      });
      html += '</div>';
    }

    if (data.refs && data.refs.length) {
      html += '<div class="detail-section"><h3>&#x1F517; References</h3><div class="file-list">';
      data.refs.forEach(r => { html += `<span class="ref-tag">${esc(r.ref_type)}: ${esc(r.ref_value)}</span>`; });
      html += '</div></div>';
    }

    if (data.recent_output && data.recent_output.length) {
      html += '<div class="detail-section"><h3>&#x1F4DF; Recent Output</h3>';
      html += '<pre style="background:var(--surface2);border-radius:6px;padding:12px;font-size:13px;font-family:\'Cascadia Code\',\'Fira Code\',monospace;color:var(--text2);overflow-x:auto;white-space:pre-wrap;max-height:300px;overflow-y:auto">';
      data.recent_output.forEach(line => { html += esc(line) + '\n'; });
      html += '</pre></div>';
    }

    if (data.turns && data.turns.length) {
      html += '<div class="detail-section"><h3>&#x1F4AC; Conversation (last 10)</h3>';
      data.turns.forEach(t => {
        const u = (t.user_message || '').substring(0, 250);
        const a = (t.assistant_response || '').substring(0, 250);
        html += `<div class="turn-item">
          <div class="turn-user">&#x1F464; ${esc(u)}${t.user_message && t.user_message.length > 250 ? '...' : ''}</div>
          <div class="turn-assistant">&#x1F916; ${esc(a)}${t.assistant_response && t.assistant_response.length > 250 ? '...' : ''}</div>
        </div>`;
      });
      html += '</div>';
    }

    if (!html) html = '<div class="empty">No additional details for this session.</div>';
    loadedDetails[id] = html;
    detail.innerHTML = html;
  } catch(e) {
    detail.innerHTML = '<div class="empty">Error loading details.</div>';
  }
}

function copyCmd(btn, cmd) {
  navigator.clipboard.writeText(cmd).then(() => {
    btn.innerHTML = '&#x2705; Copied';
    btn.classList.add('copied');
    setTimeout(() => { btn.innerHTML = '&#x1F4CB; Copy'; btn.classList.remove('copied'); }, 2000);
  });
}

async function focusSession(sid) {
  try {
    const resp = await fetch('/api/focus/' + sid, { method: 'POST' });
    const data = await resp.json();
    if (!data.success) { console.warn('Focus failed:', data.message); }
  } catch(e) { console.error('Focus error:', e); }
}

function esc(s) {
  if (!s) return '';
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}

// ===== TILE RENDERING =====
function renderTilePanel(panelId, sessions, isActive) {
  const panel = document.getElementById(panelId);
  if (!sessions.length) {
    panel.innerHTML = `<div class="empty">${isActive ? 'No active sessions detected.' : 'No previous sessions.'}</div>`;
    return;
  }

  const stateIcons = { waiting: '&#x23F3;', working: '&#x2692;&#xFE0F;', thinking: '&#x1F914;', idle: '&#x1F535;', unknown: '' };
  const stateCls = { waiting: 'waiting-tile', working: 'active-tile', thinking: 'active-tile', idle: 'idle-tile', unknown: '' };

  let html = '<div class="tile-grid">';
  for (const s of sessions) {
    const isRunning = !!runningPids[s.id];
    const pinfo = isRunning ? (runningPids[s.id] || {}) : {};
    const state = isRunning ? (pinfo.state || 'unknown') : '';
    const isWaiting = isRunning && state === 'waiting';
    const isIdle = isRunning && state === 'idle';
    const tileClass = isRunning ? (stateCls[state] || '') : '';

    html += `
      <div class="tile-card ${tileClass}" onclick="openTileDetail('${s.id}', '${esc(s.summary || '(Untitled)')}')">
        <div class="tile-subtitle" style="font-size:11px;opacity:0.6">${esc(s.group || 'General')}</div>
        <div class="tile-top">
          ${isRunning ? `<span class="live-dot ${isWaiting ? 'waiting' : (isIdle ? 'idle' : '')}" style="flex-shrink:0"></span>` : ''}
          <div class="tile-title">${isRunning && s.intent ? '&#x1F916; ' + esc(s.intent) : esc(s.summary || '(Untitled session)')}</div>
          ${isRunning && pinfo.yolo ? `<span class="badge badge-yolo" style="flex-shrink:0">&#x1F525;</span>` : ''}
        </div>
        ${isRunning && s.intent ? `<div class="tile-subtitle" style="opacity:0.7">${esc(s.summary || '')}</div>` : ''}
        <div class="tile-subtitle">started ${esc(s.created_ago)}${s.branch ? ' &bull; ' + esc(s.branch) : ''}</div>
        ${s.recent_activity ? `<div class="tile-subtitle" style="color:var(--accent)">${esc(s.recent_activity)}</div>` : ''}
        ${isWaiting && pinfo.waiting_context ? `<div class="tile-subtitle" style="color:var(--yellow)">${esc(pinfo.waiting_context.substring(0, 80))}${pinfo.waiting_context.length > 80 ? '...' : ''}</div>` : ''}
        <div class="tile-meta">
          ${isRunning && state ? `<span class="badge ${({'waiting':'badge-waiting','working':'badge-working','thinking':'badge-thinking','idle':'badge-idle'})[state] || 'badge-active'}">${stateIcons[state] || ''} ${state}</span>` : ''}
          ${isRunning && pinfo.bg_tasks ? `<span class="badge badge-bg">&#x2699;&#xFE0F; ${pinfo.bg_tasks} bg</span>` : ''}
          <span class="badge badge-turns">&#x1F4AC; ${s.turn_count}</span>
          ${s.mcp_servers && s.mcp_servers.length ? s.mcp_servers.map(m => `<span class="badge badge-mcp">&#x1F50C; ${esc(m)}</span>`).join('') : ''}
          ${isRunning ? `<span class="badge badge-focus" onclick="event.stopPropagation(); focusSession('${s.id}')" title="Focus terminal window">&#x1F4FA;</span>` : ''}
        </div>
      </div>`;
  }
  html += '</div>';
  panel.innerHTML = html;
}

async function openTileDetail(id, title) {
  document.getElementById('detail-modal-title').innerHTML = esc(title);
  const body = document.getElementById('detail-modal-body');
  body.innerHTML = '<div class="loading">Loading...</div>';
  document.getElementById('detail-modal').classList.add('open');

  try {
    const resp = await fetch('/api/session/' + id);
    const data = await resp.json();
    let html = '';

    if (data.checkpoints && data.checkpoints.length) {
      html += '<div class="detail-section"><h3>&#x1F3C1; Checkpoints</h3>';
      data.checkpoints.forEach(cp => {
        html += `<div class="checkpoint">
          <div class="cp-title">#${cp.checkpoint_number}: ${esc(cp.title || 'Checkpoint')}</div>
          ${cp.overview ? `<div class="cp-body">${esc(cp.overview)}</div>` : ''}
          ${cp.next_steps ? `<div class="cp-body" style="margin-top:4px;color:var(--yellow)"><strong>Next:</strong> ${esc(cp.next_steps)}</div>` : ''}
        </div>`;
      });
      html += '</div>';
    }

    if (data.refs && data.refs.length) {
      html += '<div class="detail-section"><h3>&#x1F517; References</h3><div class="file-list">';
      data.refs.forEach(r => { html += `<span class="ref-tag">${esc(r.ref_type)}: ${esc(r.ref_value)}</span>`; });
      html += '</div></div>';
    }

    if (data.recent_output && data.recent_output.length) {
      html += '<div class="detail-section"><h3>&#x1F4DF; Recent Output</h3>';
      html += '<pre style="background:var(--surface2);border-radius:6px;padding:12px;font-size:13px;font-family:\'Cascadia Code\',\'Fira Code\',monospace;color:var(--text2);overflow-x:auto;white-space:pre-wrap;max-height:300px;overflow-y:auto">';
      data.recent_output.forEach(line => { html += esc(line) + '\n'; });
      html += '</pre></div>';
    }

    if (data.turns && data.turns.length) {
      html += '<div class="detail-section"><h3>&#x1F4AC; Conversation (last 10)</h3>';
      data.turns.forEach(t => {
        const u = (t.user_message || '').substring(0, 250);
        const a = (t.assistant_response || '').substring(0, 250);
        html += `<div class="turn-item">
          <div class="turn-user">&#x1F464; ${esc(u)}${t.user_message && t.user_message.length > 250 ? '...' : ''}</div>
          <div class="turn-assistant">&#x1F916; ${esc(a)}${t.assistant_response && t.assistant_response.length > 250 ? '...' : ''}</div>
        </div>`;
      });
      html += '</div>';
    }

    if (!html) html = '<div class="empty">No additional details for this session.</div>';
    body.innerHTML = html;
  } catch(e) {
    body.innerHTML = '<div class="empty">Error loading details.</div>';
  }
}

function closeDetailModal() {
  document.getElementById('detail-modal').classList.remove('open');
}

// ===== SEARCH =====
document.getElementById('search').addEventListener('input', () => render());

// ===== POLLING =====
// Active sessions: refresh process list every 5s
// Full session list: refresh every 30s
fetchSessions();
initView();
updateNotifBtn();
activeTimer = setInterval(fetchProcesses, 5000);
previousTimer = setInterval(fetchSessions, 30000);
</script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# API Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template_string(TEMPLATE, version=__version__)


@app.route("/api/sessions")
def api_sessions():
    db = get_db()
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
        s["restart_cmd"] = build_restart_command(s, yolo=had_yolo)
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
    db = get_db()
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
    db.close()
    return jsonify({
        "checkpoints": [dict(r) for r in checkpoints],
        "refs": [dict(r) for r in refs],
        "turns": [dict(r) for r in reversed(list(turns))],
        "recent_output": get_recent_output(session_id),
    })


@app.route("/api/processes")
def api_processes():
    """Return currently running copilot sessions mapped by session ID."""
    return jsonify(get_running_sessions())


@app.route("/api/focus/<session_id>", methods=["POST"])
def api_focus(session_id):
    """Focus the terminal window for a running session."""
    success, message = focus_session_window(session_id)
    return jsonify({"success": success, "message": message})


@app.route("/favicon.svg")
def favicon():
    """Serve an inline SVG favicon."""
    svg = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">
  <defs><linearGradient id="g" x1="0%" y1="0%" x2="100%" y2="100%">
    <stop offset="0%" style="stop-color:#58a6ff"/>
    <stop offset="100%" style="stop-color:#bc8cff"/>
  </linearGradient></defs>
  <rect width="32" height="32" rx="6" fill="#161b22"/>
  <circle cx="11" cy="13" r="2.5" fill="url(#g)"/>
  <circle cx="21" cy="13" r="2.5" fill="url(#g)"/>
  <path d="M9 20 Q16 26 23 20" stroke="url(#g)" stroke-width="2" fill="none" stroke-linecap="round"/>
</svg>'''
    return svg, 200, {"Content-Type": "image/svg+xml"}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=5111)
    args = parser.parse_args()
    print(f"  Copilot Session Dashboard")
    print(f"  Reading from: {DB_PATH}")
    print(f"  Open http://localhost:{args.port}")
    app.run(host="127.0.0.1", port=args.port, debug=False)
