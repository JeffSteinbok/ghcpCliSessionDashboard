---
title: Features
layout: default
nav_order: 4
---

# Features
{: .no_toc }

## Table of contents
{: .no_toc .text-delta }

1. TOC
{:toc}

---

## Session Monitoring

The dashboard shows all your Copilot CLI and Claude Code sessions with real-time state indicators:

| State | Indicator | Meaning |
|:------|:----------|:--------|
| **Working / Thinking** | 🟢 Green | Session is actively running tools or reasoning |
| **Waiting** | 🟡 Yellow | Session needs your input (`ask_user` or `ask_permission` pending) |
| **Idle** | 🔵 Blue | Session is done and ready for your next task |

## Claude Code Support

{: .new }
> New in v0.7

The dashboard automatically discovers **Claude Code** sessions from `~/.claude/projects/`. Active Claude sessions appear alongside Copilot sessions with a distinctive `✦ Claude` badge.

## Desktop Notifications

Get browser notifications when sessions transition between states — so you know immediately when a session needs attention or finishes its work.

## Focus Window

Click the focus button on any active session to bring its terminal window to the foreground. No more hunting through your taskbar to find the right terminal.

## Restart Commands

Every session shows a copy-pasteable restart command:

```bash
copilot --resume <session-id>
```

Quickly resume any session that's been interrupted.

## Waiting Context

When a session is in the **Waiting** state, the dashboard shows exactly *what* it's asking — the `ask_user` question, available choices, or `ask_permission` details.

## Background Tasks

Sessions running sub-agents show a count of active background tasks, so you can see at a glance how much work is in progress.

## Session Details

Click any session to expand its detail view:

- **Checkpoints** — milestone summaries of work completed
- **Recent tool output** — latest commands and results
- **References** — linked PRs, issues, and commits
- **Conversation history** — full turn-by-turn dialogue

## Views

### Tile View

A compact card grid showing session state, summary, branch, MCP servers, and quick actions. Great for monitoring many sessions at once.

### List View

Detailed expandable rows with more metadata visible at a glance. Better for drilling into individual sessions.

## Theming

- **9 color palettes** — choose your preferred accent colors
- **Light and dark mode** — toggle with one click
- **Persistent preferences** — your choices are saved across sessions

## Session Filtering

Filter sessions by name, repository, branch, MCP server, or directory using the search bar at the top of the dashboard.

## Tabs

| Tab | Shows |
|:----|:------|
| **Active** | Currently running sessions with live state |
| **Previous** | Completed sessions from session history |
| **Timeline** | Chronological view of session activity |
| **Files** | Most-edited files across all sessions |

## Settings Menu

The ☰ hamburger menu in the header provides quick access to:

- Autostart-on-login toggle
- Remote sync configuration
- Server information
