# Copilot Session Dashboard
[![GitHub](https://img.shields.io/badge/GitHub-ghcpCliSessionDashboard-blue?logo=github)](https://github.com/JeffSteinbok/ghcpCliSessionDashboard)
[![GitHub release](https://img.shields.io/github/v/release/JeffSteinbok/ghcpCliSessionDashboard)](https://github.com/JeffSteinbok/ghcpCliSessionDashboard/releases)

[![CI](https://github.com/JeffSteinbok/ghcpCliSessionDashboard/actions/workflows/ci.yml/badge.svg)](https://github.com/JeffSteinbok/ghcpCliSessionDashboard/actions/workflows/ci.yml)
[![Release](https://github.com/JeffSteinbok/ghcpCliSessionDashboard/actions/workflows/release.yml/badge.svg)](https://github.com/JeffSteinbok/ghcpCliSessionDashboard/actions/workflows/release.yml)

[![Publish to PyPI](https://github.com/JeffSteinbok/ghcpCliSessionDashboard/actions/workflows/publish-pypi.yml/badge.svg)](https://github.com/JeffSteinbok/ghcpCliSessionDashboard/actions/workflows/publish-pypi.yml)
[![PyPI version](https://img.shields.io/pypi/v/ghcp-cli-dashboard.svg)](https://pypi.org/project/ghcp-cli-dashboard/)

A local web dashboard that monitors all your GitHub Copilot CLI sessions in real-time.
Designed for power users running multiple Copilot sessions simultaneously.

![Dashboard Screenshot](https://raw.githubusercontent.com/JeffSteinbok/ghcpCliSessionDashboard/main/screenshot.png)

> [!IMPORTANT]
> The dashboard requires the **SESSION_STORE** experimental feature to be enabled in the Copilot CLI. Without it, session history will not be available. Add `"experimental": true` to `~/.copilot/config.json`, then start a new Copilot session. The `session-store.db` file will be created automatically on first run.

## Installation

### Option 1: From PyPI

```bash
pip install ghcp-cli-dashboard
```

### Option 2: From Source

```bash
# Clone the repo
git clone https://github.com/JeffSteinbok/ghcpCliDashboard.git
cd ghcpCliDashboard

# Install in editable mode
pip install -e .
```

## Usage

```bash
# Start the dashboard
copilot-dashboard start

# Start in background
copilot-dashboard start --background

# Check status
copilot-dashboard status

# Stop
copilot-dashboard stop
```

Open **http://localhost:5111** in your browser.

## Features

### Session States
- **Working / Thinking** (green) — session is actively running tools or reasoning
- **Waiting** (yellow) — session needs your input (`ask_user` or `ask_permission` pending)
- **Idle** (blue) — session is done and ready for your next task

### Desktop Notifications
Click the 🔕 button in the header to enable browser notifications. You'll get an alert whenever a session transitions from working to waiting or idle, so you can stay on top of sessions that need attention without watching the dashboard.

### Views
- **Tile view** (default) — compact card grid to see all sessions at a glance
- **List view** — detailed expandable rows with full session info
- Toggle between views with the buttons next to the Active/Previous tabs

### Session Monitoring
- **Active vs Previous** — sessions with a running `copilot.exe` process appear in the Active tab
- **Waiting context** — when a session is waiting, shows *what* it's asking (e.g. the `ask_user` question and choices)
- **Background tasks** — shows count of running subagents per session
- **YOLO mode indicator** — shows 🔥 YOLO badge for sessions running with `--yolo`
- **MCP servers** — displays connected MCP servers (e.g. bluebird, icm, github) for both active and past sessions
- **Project grouping** — sessions are auto-categorized by repo, working directory, or content analysis

### Actions
- **Focus window** — click 📺 on an active session to bring its terminal window to the foreground
- **Restart commands** — each session has a copy-pasteable `copilot --resume <id>` command (includes `--yolo` only if the session was running with it)
- **Session details** — click any session to see checkpoints, recent tool output, references, and conversation history

### Appearance
- **Light/Dark mode** toggle
- **Color palettes** — Default and Pink themes
- **Auto-refresh** — active sessions poll every 5s, full session list every 30s; expanded sections and collapsed groups persist across refreshes

## Prerequisites

| Package | Purpose |
|---------|---------|
| `flask` | Web server |
| `pywin32` | Window focus and process detection (Windows-only) |

Both are installed automatically via `pip install ghcp-cli-dashboard`.

For more details on architecture, data sources, and API endpoints, see [DEVELOPMENT.md](DEVELOPMENT.md).
