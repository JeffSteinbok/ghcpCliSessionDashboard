"""
Copilot Dashboard - CLI entry point.
Provides start, stop, and status subcommands.

Requires Python >= 3.12.
"""

import argparse
import os
import shutil
import signal
import subprocess
import sys

if sys.version_info < (3, 12):
    sys.exit("Error: Python >= 3.12 is required. Found: " + sys.version)

PKG_DIR = os.path.dirname(os.path.abspath(__file__))
PID_FILE = os.path.join(PKG_DIR, ".dashboard.pid")
DEFAULT_PORT = 5111

from .__version__ import __repository__, __version__  # noqa: E402

BANNER = f"""\
  Copilot Dashboard v{__version__}
  By Jeff Steinbok — {__repository__}
  Open http://localhost:{{port}}
"""


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
                [py, "-3", "--version"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
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


def cmd_serve(args):
    """Internal: run the Flask app in-process (used by --background)."""
    from .dashboard_app import app

    app.run(host="127.0.0.1", port=args.port, debug=False)


def cmd_start(args):
    """Start the dashboard server."""
    # Check if already running
    if os.path.exists(PID_FILE):
        with open(PID_FILE, encoding="utf-8") as f:
            old_pid = int(f.read().strip())
        try:
            os.kill(old_pid, 0)
            print(f"Dashboard already running (PID {old_pid}) at http://localhost:{args.port}")
            return
        except OSError:
            os.remove(PID_FILE)

    if args.background:
        python = _find_python()
        # Re-invoke as a module so relative imports work
        pkg = __spec__.parent if __spec__ else None
        if pkg:
            repo_root = os.path.dirname(PKG_DIR)
            cmd = [
                python,
                "-m",
                f"{pkg}.session_dashboard",
                "_serve",
                "--port",
                str(args.port),
            ]
        else:
            cmd = [
                python,
                "-m",
                "src.session_dashboard",
                "_serve",
                "--port",
                str(args.port),
            ]
            repo_root = os.path.dirname(PKG_DIR)
        proc = subprocess.Popen(  # pylint: disable=consider-using-with
            cmd,
            cwd=repo_root,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        with open(PID_FILE, "w", encoding="utf-8") as f:
            f.write(str(proc.pid))
        print(f"Dashboard started in background (PID {proc.pid})")
        print(BANNER.format(port=args.port))
    else:
        # Foreground - write PID for status checks, run directly
        with open(PID_FILE, "w", encoding="utf-8") as f:
            f.write(str(os.getpid()))
        try:
            from .dashboard_app import app

            print(BANNER.format(port=args.port))
            app.run(host="127.0.0.1", port=args.port, debug=False)
        finally:
            if os.path.exists(PID_FILE):
                os.remove(PID_FILE)


def cmd_stop(_args):
    """Stop the dashboard server."""
    if not os.path.exists(PID_FILE):
        print("Dashboard is not running (no PID file found).")
        return

    with open(PID_FILE, encoding="utf-8") as f:
        pid = int(f.read().strip())

    try:
        if sys.platform == "win32":
            subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True, check=False)
        else:
            os.kill(pid, signal.SIGTERM)
        print(f"Dashboard stopped (PID {pid}).")
    except Exception as e:
        print(f"Could not stop process {pid}: {e}")
    finally:
        if os.path.exists(PID_FILE):
            os.remove(PID_FILE)


def cmd_status(_args):
    """Check if the dashboard is running."""
    if not os.path.exists(PID_FILE):
        print("Dashboard is not running.")
        return

    with open(PID_FILE, encoding="utf-8") as f:
        pid = int(f.read().strip())

    try:
        os.kill(pid, 0)
        print(f"Dashboard is running (PID {pid}) at http://localhost:{DEFAULT_PORT}")
    except OSError:
        print("Dashboard PID file exists but process is not running. Cleaning up.")
        os.remove(PID_FILE)


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="copilot-dashboard",
        description="Copilot Dashboard - monitor all your Copilot CLI sessions",
        epilog=(
            "Examples:\n"
            "  copilot-dashboard start                  Start in foreground\n"
            "  copilot-dashboard start --background     Start as background process\n"
            "  copilot-dashboard start -b --port 8080   Background on custom port\n"
            "  copilot-dashboard stop                   Stop the background server\n"
            "  copilot-dashboard status                 Check if server is running\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command")

    start_p = sub.add_parser("start", help="Start the dashboard web server")
    start_p.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"Port to listen on (default: {DEFAULT_PORT})")
    start_p.add_argument("--background", "-b", action="store_true", help="Run as a background process (detached)")

    sub.add_parser("stop", help="Stop the background dashboard server")
    sub.add_parser("status", help="Check if the dashboard server is running")

    serve_p = sub.add_parser("_serve", help=argparse.SUPPRESS)
    serve_p.add_argument("--port", type=int, default=DEFAULT_PORT)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return

    {
        "start": cmd_start,
        "_serve": cmd_serve,
        "stop": cmd_stop,
        "status": cmd_status,
    }[args.command](args)


if __name__ == "__main__":
    main()
