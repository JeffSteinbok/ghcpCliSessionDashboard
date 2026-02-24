# Development Guide

## Dependencies

| Package | Purpose |
|---------|---------|
| `flask` | Web server |
| `pywin32` | Window focus and process detection (Windows-only) |

Both are installed automatically when you `pip install ghcp-cli-dashboard`. For source installs, run `pip install -r requirements.txt` (plus `pip install pywin32` on Windows).

## Architecture

| Module | Role |
|--------|------|
| `session_dashboard.py` | CLI entry point with `start`, `stop`, `status` subcommands |
| `dashboard_app.py` | Flask app with REST API and embedded HTML/JS/CSS single-page dashboard |
| `process_tracker.py` | Detects running copilot processes, reads `events.jsonl` for session state, extracts MCP servers, and uses Win32 APIs for window focus |

## Data Sources

| Source | What it provides |
|--------|-----------------|
| `~/.copilot/session-store.db` | Session metadata, turns, checkpoints, files, refs (read-only SQLite) |
| `~/.copilot/session-state/<id>/events.jsonl` | Live session state, MCP config, recent tool output |
| Running `copilot.exe` processes | Active session detection, `--yolo` flag, MCP config file paths |

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Dashboard UI |
| `/api/sessions` | GET | All sessions with metadata, groups, restart commands |
| `/api/session/<id>` | GET | Session detail (checkpoints, refs, recent output, turns) |
| `/api/processes` | GET | Currently running sessions with state, yolo, MCP |
| `/api/focus/<id>` | POST | Bring session's terminal window to foreground |
