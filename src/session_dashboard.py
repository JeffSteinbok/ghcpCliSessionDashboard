"""
Copilot Dashboard - CLI entry point.
Provides start, stop, and status subcommands.
"""

import argparse
import os
import shutil
import signal
import subprocess
import sys

from .constants import (
    DASHBOARD_LOG_FILE,
    DEFAULT_PORT,
    LOCALHOST,
    MIN_PYTHON_VERSION,
    PYTHON_VERSION_TIMEOUT,
)
from .logging_config import setup_logging

PKG_DIR = os.path.dirname(os.path.abspath(__file__))
PID_FILE = os.path.join(PKG_DIR, ".dashboard.pid")

from .__version__ import __repository__, __version__  # noqa: E402

BANNER = f"""\
  Copilot Dashboard v{__version__}
  By Jeff Steinbok — {__repository__}
  Open http://localhost:{{port}}
  Log file: {DASHBOARD_LOG_FILE}
"""


def _print_sync_info(sync_folder) -> None:  # type: ignore[no-untyped-def]
    """Print sync folder status on startup."""
    if sync_folder:
        print(f"  [sync] Sync folder: {sync_folder}")
        print('     Configure: set "sync.folder" in ~/.copilot/dashboard-config.json')
        print('     Disable:   set "sync.enabled" to false in ~/.copilot/dashboard-config.json')
    else:
        print("  [sync] Sync: disabled (no OneDrive/cloud folder detected)")
        print(
            '     Enable: set "sync.folder" to a cloud-synced path in ~/.copilot/dashboard-config.json'
        )
    print()


def _find_python():
    """Find a suitable Python interpreter, preferring the py launcher on Windows.

    Returns a list of command parts (e.g. ["py", "-3"] or ["/usr/bin/python3.13"]).
    """
    if sys.version_info >= MIN_PYTHON_VERSION:
        return [sys.executable]

    # Try the py launcher (Windows)
    py = shutil.which("py")
    if py:
        try:
            result = subprocess.run(
                [py, "-3", "--version"],
                capture_output=True,
                text=True,
                timeout=PYTHON_VERSION_TIMEOUT,
                check=False,
            )
            if result.returncode == 0:
                ver = result.stdout.strip().split()[-1]  # "3.14.3"
                major, minor = (int(x) for x in ver.split(".")[:2])
                if major >= MIN_PYTHON_VERSION[0] and minor >= MIN_PYTHON_VERSION[1]:
                    return [py, "-3"]
        except Exception:
            pass

    # Fallback: search PATH for python3.x
    for minor in range(14, 10, -1):
        candidate = shutil.which(f"python3.{minor}")
        if candidate:
            return [candidate]

    return [sys.executable]


def _read_pid_file() -> int | None:
    """Read PID from the PID file, returning None if corrupt or missing."""
    if not os.path.exists(PID_FILE):
        return None
    try:
        with open(PID_FILE, encoding="utf-8") as f:
            return int(f.read().strip())
    except (ValueError, OSError):
        return None


def cmd_serve(args):
    """Internal: run the uvicorn server in-process (used by --background)."""
    import uvicorn

    from .sync import resolve_sync_folder

    setup_logging(level=getattr(args, "log_level", None))
    _print_sync_info(resolve_sync_folder())
    uvicorn.run(
        "src.dashboard_api:app",
        host=LOCALHOST,
        port=args.port,
        log_level="warning",
    )


def cmd_start(args):
    """Start the dashboard server."""
    # Check if already running
    old_pid = _read_pid_file()
    if old_pid is not None:
        try:
            os.kill(old_pid, 0)
            print(f"Dashboard already running (PID {old_pid}) at http://localhost:{args.port}")
            return
        except OSError:
            os.remove(PID_FILE)

    if args.background:
        python = _find_python()
        log_level = getattr(args, "log_level", None)
        # Re-invoke as a module so relative imports work
        pkg = __spec__.parent if __spec__ else None
        if pkg:
            repo_root = os.path.dirname(PKG_DIR)
            cmd = [
                *python,
                "-m",
                f"{pkg}.session_dashboard",
                "_serve",
                "--port",
                str(args.port),
            ]
        else:
            cmd = [
                *python,
                "-m",
                "src.session_dashboard",
                "_serve",
                "--port",
                str(args.port),
            ]
            repo_root = os.path.dirname(PKG_DIR)
        if log_level:
            cmd.extend(["--log-level", log_level])
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
            import uvicorn

            from .sync import resolve_sync_folder

            setup_logging(level=getattr(args, "log_level", None))
            print(BANNER.format(port=args.port))
            _print_sync_info(resolve_sync_folder())
            uvicorn.run(
                "src.dashboard_api:app",
                host=LOCALHOST,
                port=args.port,
                log_level="warning",
            )
        finally:
            if os.path.exists(PID_FILE):
                os.remove(PID_FILE)


def cmd_stop(_args):
    """Stop the dashboard server."""
    pid = _read_pid_file()
    if pid is None:
        print("Dashboard is not running (no PID file found).")
        return

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


def cmd_upgrade(_args):
    """Upgrade the dashboard via pip and restart if it was running."""
    from .__version__ import __version__ as old_version

    # Remember if server was running (and on which port) so we can restart
    pid = _read_pid_file()
    was_running = False
    port = DEFAULT_PORT
    if pid is not None:
        try:
            os.kill(pid, 0)
            was_running = True
            # Try to read port from the running server
            try:
                import urllib.request

                with urllib.request.urlopen(
                    f"http://{LOCALHOST}:{DEFAULT_PORT}/api/server-info", timeout=3
                ) as resp:
                    import json

                    info = json.loads(resp.read())
                    port = int(info.get("port", DEFAULT_PORT))
            except Exception:
                pass
        except OSError:
            pass

    # Stop the server first to release file locks (important on Windows)
    if was_running:
        print(f"Stopping dashboard (PID {pid})…")
        try:
            if sys.platform == "win32":
                subprocess.run(
                    ["taskkill", "/F", "/PID", str(pid)], capture_output=True, check=False
                )
            else:
                os.kill(pid, signal.SIGTERM)
        except Exception:
            pass
        if os.path.exists(PID_FILE):
            os.remove(PID_FILE)

    # Run pip upgrade
    print("Upgrading ghcp-cli-dashboard…")
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--no-cache-dir",
            "--upgrade",
            "ghcp-cli-dashboard",
        ],
        check=False,
    )
    if result.returncode != 0:
        print("Upgrade failed.")
        return

    # Report version change
    try:
        ver_out = subprocess.run(
            [sys.executable, "-c", "from src.__version__ import __version__; print(__version__)"],
            capture_output=True,
            text=True,
            check=False,
        )
        new_version = ver_out.stdout.strip() if ver_out.returncode == 0 else "unknown"
    except Exception:
        new_version = "unknown"
    print(f"Upgraded: v{old_version} → v{new_version}")

    # Restart if it was running
    if was_running:
        print(f"Restarting dashboard on port {port}…")
        cmd = shutil.which("copilot-dashboard")
        if cmd:
            kwargs: dict = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
            if sys.platform == "win32":
                kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW | 0x00000008
            else:
                kwargs["start_new_session"] = True
            subprocess.Popen([cmd, "start", "--background", "--port", str(port)], **kwargs)
            print(f"Dashboard restarted at http://localhost:{port}")
            print("Please refresh your browser to pick up the new version.")
        else:
            print("Could not find copilot-dashboard command to restart. Start it manually.")


def cmd_status(_args):
    """Check if the dashboard is running."""
    pid = _read_pid_file()
    if pid is None:
        print("Dashboard is not running.")
        return

    try:
        os.kill(pid, 0)
        print(f"Dashboard is running (PID {pid})")
    except OSError:
        print("Dashboard PID file exists but process is not running. Cleaning up.")
        os.remove(PID_FILE)


TASK_NAME = "CopilotDashboard"
"""Windows registry value name under HKCU\\...\\Run for autostart."""

_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def _get_autostart_cmd_str(port: int) -> str:
    """Build the command string for the Run registry value."""
    cmd = shutil.which("copilot-dashboard")
    if cmd:
        return f'"{cmd}" start --background --port {port}'
    return f'"{sys.executable}" -m src.session_dashboard start --background --port {port}'


def cmd_autostart(args):
    """Register the dashboard to start automatically at login."""
    if sys.platform != "win32":
        print("Error: autostart is currently only supported on Windows.")
        print("macOS and Linux support is planned for a future release.")
        sys.exit(1)

    import winreg

    port = args.port
    cmd_str = _get_autostart_cmd_str(port)

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, TASK_NAME, 0, winreg.REG_SZ, cmd_str)
        print(f"Autostart enabled — dashboard will start on login (port {port}).")
        print(f"  Registry: HKCU\\{_RUN_KEY}\\{TASK_NAME}")
        print(f"  Command:  {cmd_str}")
        print("To remove: copilot-dashboard autostart-remove")
    except OSError as e:
        print(f"Failed to set registry key: {e}")
        sys.exit(1)


def cmd_autostart_remove(_args):
    """Remove the dashboard autostart registry entry."""
    if sys.platform != "win32":
        print("Error: autostart is currently only supported on Windows.")
        print("macOS and Linux support is planned for a future release.")
        sys.exit(1)

    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, TASK_NAME)
        print(f"Autostart removed — registry value '{TASK_NAME}' deleted.")
    except FileNotFoundError:
        print("Autostart is not currently configured (no registry entry found).")
    except OSError as e:
        print(f"Failed to remove registry entry: {e}")
        sys.exit(1)


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
            "  copilot-dashboard upgrade                Upgrade to latest version\n"
            "  copilot-dashboard autostart              Start on login (Windows)\n"
            "  copilot-dashboard autostart-remove       Remove login startup\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command")

    start_p = sub.add_parser("start", help="Start the dashboard web server")
    start_p.add_argument(
        "--port",
        type=int,
        default=DEFAULT_PORT,
        help=f"Port to listen on (default: {DEFAULT_PORT})",
    )
    start_p.add_argument(
        "--background", "-b", action="store_true", help="Run as a background process (detached)"
    )
    start_p.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default=None,
        help="Logging verbosity (default: INFO, or value from config)",
    )

    sub.add_parser("stop", help="Stop the background dashboard server")
    sub.add_parser("status", help="Check if the dashboard server is running")
    sub.add_parser("upgrade", help="Upgrade to the latest version from PyPI")

    autostart_p = sub.add_parser(
        "autostart", help="Start dashboard automatically at login (Windows)"
    )
    autostart_p.add_argument(
        "--port",
        type=int,
        default=DEFAULT_PORT,
        help=f"Port for the autostarted dashboard (default: {DEFAULT_PORT})",
    )
    sub.add_parser("autostart-remove", help="Remove the login autostart task")

    serve_p = sub.add_parser("_serve", help=argparse.SUPPRESS)
    serve_p.add_argument("--port", type=int, default=DEFAULT_PORT)
    serve_p.add_argument("--log-level", choices=["DEBUG", "INFO", "WARNING", "ERROR"], default=None)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return

    {
        "start": cmd_start,
        "_serve": cmd_serve,
        "stop": cmd_stop,
        "status": cmd_status,
        "upgrade": cmd_upgrade,
        "autostart": cmd_autostart,
        "autostart-remove": cmd_autostart_remove,
    }[args.command](args)


if __name__ == "__main__":
    main()
