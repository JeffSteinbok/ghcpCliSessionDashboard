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

### Building the Frontend

The React/TypeScript frontend **must be built before starting the server**. The build output goes to `src/static/dist/` which the Python server serves as static files.

```powershell
cd frontend
npm install    # first time or after package.json changes
npm run build  # compiles to ../src/static/dist/
cd ..
```

Always rebuild the frontend after any changes to files under `frontend/src/`. If the dashboard shows a blank page or missing UI, the frontend likely needs to be rebuilt.

For active frontend development, you can run the Vite dev server (`npm run dev` in `frontend/`) which proxies API calls to `http://localhost:5112` — but the Python backend must still be running.

### Starting the Backend (fresh or restart)

Always kill the existing server first, then start a new one. The `start` command detects an existing server and won't respawn if it's already running.

**Important:** The server mounts `src/static/dist/assets/` at startup. If the frontend hasn't been built yet, the `/assets` route won't exist and the UI will be blank. **Always build the frontend before starting the server.**

**PowerShell — kill then restart using `_serve` directly with `detach: true`:**
```powershell
$conn = Get-NetTCPConnection -LocalPort 5112 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if ($conn) { Stop-Process -Id $conn.OwningProcess -Force; Start-Sleep 2 }
python -m src.session_dashboard _serve --port 5112
```

Use `mode="async"`, `detach=true` so the server survives session cleanup. Verify with:
```powershell
Start-Sleep 4; curl -s -o NUL -w "%{http_code}" http://127.0.0.1:5112/
```

**Key: use `_serve` not `start`.** The `start` subcommand spawns a child then exits — the child gets orphaned when the shell dies. `_serve` runs uvicorn directly and survives as a detached process.

### Full Dev Startup Sequence (always follow this)

When asked to "start the dashboard", "start in dev mode", or similar — **always run all three steps**:

```powershell
# 1. Build frontend (MUST happen before server start)
cd frontend && npm install --silent && npm run build && cd ..

# 2. Kill existing server on port 5112
$conn = Get-NetTCPConnection -LocalPort 5112 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if ($conn) { Stop-Process -Id $conn.OwningProcess -Force; Start-Sleep 2 }

# 3. Start backend (mode="async", detach=true)
python -m src.session_dashboard _serve --port 5112
```

After starting, verify the server is up **and** assets are served:
```powershell
Start-Sleep 4
curl -s -o NUL -w "%{http_code}" http://127.0.0.1:5112/          # should be 200
curl -s -o NUL -w "%{http_code}" http://127.0.0.1:5112/api/sessions  # should be 200
```

## Shipping a New Version

When asked to "commit and ship" or "make a release", follow these steps in order:

1. **Commit & push** all pending changes to the current branch.
2. **Create a PR** against `main` with a clear, descriptive title and body summarizing the changes.
3. **Wait for CI/policy checks** to pass. Poll the PR status until all required checks are green.
4. **Approve the PR**, then **squash-merge** it into `main`.
5. **Delete the source branch** after merge.
6. **Create a new GitHub release** on `main`:
   - Use the next appropriate semver tag (bump minor for features, patch for fixes).
   - Write a release description highlighting changes since the last release (use commit log / PR descriptions).
   - Mark it as **Latest release**.

