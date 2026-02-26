# Copilot Instructions

## Linting & Code Quality

All code changes must pass the following checks before committing:

```bash
ruff check src/       # linting
ruff format src/      # formatting
mypy src/             # type checking
```

Run these after making any changes to Python files in `src/`. Fix all errors before considering the task complete.

## Running the App for Development

When starting the dashboard for testing during a development session, always use port **5112** to avoid conflicting with any production instance.

### Starting fresh (or restarting)

Always kill the existing server first, then start a new one. The `start` command detects an existing server and won't respawn if it's already running.

**PowerShell — kill then restart using `_serve` directly with `detach: true`:**
```powershell
$p = Get-NetTCPConnection -LocalPort 5112 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if ($p) { Stop-Process -Id $p.OwningProcess -Force }
Start-Sleep 1
cd D:\Users\jeffs\GitHub\ghcpCliSessionDashboard-fixes
python -m src.session_dashboard _serve --port 5112
```

Use `mode="async"`, `detach=true`. Confirm with `read_powershell` — look for `* Running on http://127.0.0.1:5112` in the log file.

**Key: use `_serve` not `start`.** The `start` subcommand spawns a child then exits — the child gets orphaned when the shell dies. `_serve` runs Flask directly and survives as a detached process.

