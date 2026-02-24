"""
Copilot Session Dashboard - CLI entry point.
Provides install, start, stop, and status subcommands.

Requires Python >= 3.12.
"""

import argparse
import os
import sys
import subprocess
import signal
import shutil

if sys.version_info < (3, 12):
    sys.exit("Error: Python >= 3.12 is required. Found: " + sys.version)

PKG_DIR = os.path.dirname(os.path.abspath(__file__))
PID_FILE = os.path.join(PKG_DIR, ".dashboard.pid")
DEFAULT_PORT = 5111


def _find_python():
    """Find a Python >= 3.12 interpreter, preferring the py launcher on Windows."""
    # If the current interpreter is good enough, use it
    if sys.version_info >= (3, 12):
        return sys.executable

    # Try the py launcher (Windows)
    py = shutil.which("py")
    if py:
        try:
            result = subprocess.run(
                [py, "-3", "--version"], capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                ver = result.stdout.strip().split()[-1]  # "3.14.3"
                major, minor = (int(x) for x in ver.split(".")[:2])
                if major >= 3 and minor >= 12:
                    return f"{py} -3"
        except Exception:
            pass

    # Fallback: search PATH for python3.x
    for minor in range(14, 11, -1):
        candidate = shutil.which(f"python3.{minor}")
        if candidate:
            return candidate

    return sys.executable


def cmd_install(args):
    """Install all prerequisites."""
    print("Installing prerequisites...")
    packages = ["flask"]
    if sys.platform == "win32":
        packages.append("pywin32")
    for pkg in packages:
        print(f"  Installing {pkg}...")
        subprocess.run(
            [sys.executable, "-m", "pip", "install", pkg, "--quiet"],
            check=False,
        )
    print("Done. All prerequisites installed.")


def cmd_start(args):
    """Start the dashboard server."""
    # Check if already running
    if os.path.exists(PID_FILE):
        with open(PID_FILE) as f:
            old_pid = int(f.read().strip())
        try:
            os.kill(old_pid, 0)
            print(f"Dashboard already running (PID {old_pid}) at http://localhost:{args.port}")
            return
        except OSError:
            os.remove(PID_FILE)

    app_path = os.path.join(PKG_DIR, "dashboard_app.py")

    if args.background:
        python = _find_python()
        proc = subprocess.Popen(
            [python, app_path, "--port", str(args.port)],
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        with open(PID_FILE, "w") as f:
            f.write(str(proc.pid))
        print(f"Dashboard started in background (PID {proc.pid})")
        print(f"Open http://localhost:{args.port}")
    else:
        # Foreground - write PID for status checks, run directly
        with open(PID_FILE, "w") as f:
            f.write(str(os.getpid()))
        try:
            from .dashboard_app import app
            print(f"  Copilot Session Dashboard")
            print(f"  Open http://localhost:{args.port}")
            app.run(host="127.0.0.1", port=args.port, debug=False)
        finally:
            if os.path.exists(PID_FILE):
                os.remove(PID_FILE)


def cmd_stop(args):
    """Stop the dashboard server."""
    if not os.path.exists(PID_FILE):
        print("Dashboard is not running (no PID file found).")
        return

    with open(PID_FILE) as f:
        pid = int(f.read().strip())

    try:
        if sys.platform == "win32":
            subprocess.run(["taskkill", "/F", "/PID", str(pid)],
                           capture_output=True, check=False)
        else:
            os.kill(pid, signal.SIGTERM)
        print(f"Dashboard stopped (PID {pid}).")
    except Exception as e:
        print(f"Could not stop process {pid}: {e}")
    finally:
        if os.path.exists(PID_FILE):
            os.remove(PID_FILE)


def cmd_status(args):
    """Check if the dashboard is running."""
    if not os.path.exists(PID_FILE):
        print("Dashboard is not running.")
        return

    with open(PID_FILE) as f:
        pid = int(f.read().strip())

    try:
        os.kill(pid, 0)
        print(f"Dashboard is running (PID {pid}) at http://localhost:{DEFAULT_PORT}")
    except OSError:
        print("Dashboard PID file exists but process is not running. Cleaning up.")
        os.remove(PID_FILE)


def main():
    parser = argparse.ArgumentParser(
        prog="session-dashboard",
        description="Copilot Session Dashboard - monitor all your Copilot CLI sessions",
    )
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("install", help="Install prerequisites (flask; pywin32 on Windows)")

    start_p = sub.add_parser("start", help="Start the dashboard web server")
    start_p.add_argument("--port", type=int, default=DEFAULT_PORT)
    start_p.add_argument("--background", "-b", action="store_true",
                         help="Run in background")

    sub.add_parser("stop", help="Stop the dashboard server")
    sub.add_parser("status", help="Check if the dashboard is running")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return

    {"install": cmd_install, "start": cmd_start,
     "stop": cmd_stop, "status": cmd_status}[args.command](args)


if __name__ == "__main__":
    main()
