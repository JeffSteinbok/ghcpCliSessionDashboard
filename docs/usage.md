---
title: Usage
layout: default
nav_order: 3
---

# Usage
{: .no_toc }

## Table of contents
{: .no_toc .text-delta }

1. TOC
{:toc}

---

## Starting the Dashboard

```bash
# Start in the foreground
copilot-dashboard start

# Start in the background (detached)
copilot-dashboard start --background

# Start on a custom port (default: 5111)
copilot-dashboard start --port 8080
```

Then open **[http://localhost:5111](http://localhost:5111)** (or your custom port) in your browser.

## Managing the Server

```bash
# Check if the dashboard is running
copilot-dashboard status

# Stop a running dashboard
copilot-dashboard stop
```

## Upgrading

```bash
# Upgrade to the latest version (restarts automatically if running)
copilot-dashboard upgrade
```

This stops the server, upgrades the package via pip, and restarts it.

## Autostart at Login

{: .note }
> Autostart is currently a Windows-only feature.

```bash
# Enable autostart at login
copilot-dashboard autostart

# Autostart with a custom port
copilot-dashboard autostart --port 8080

# Remove the autostart entry
copilot-dashboard autostart-remove
```

## Command Reference

| Command | Description |
|:--------|:------------|
| `copilot-dashboard start` | Start the dashboard server |
| `copilot-dashboard start --background` | Start detached in the background |
| `copilot-dashboard start --port PORT` | Start on a custom port |
| `copilot-dashboard stop` | Stop the running dashboard |
| `copilot-dashboard status` | Check server status |
| `copilot-dashboard upgrade` | Upgrade and restart |
| `copilot-dashboard autostart` | Enable Windows login startup |
| `copilot-dashboard autostart --port PORT` | Autostart with custom port |
| `copilot-dashboard autostart-remove` | Remove login startup |
