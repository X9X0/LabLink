"""Console-free entry point for the Windows Start Menu shortcuts.

The shortcuts run this through ``pythonw.exe``, which has no console attached.
That is the point — a lab user should never see a black window — but it costs
something important: with no console, anything printed to stderr goes nowhere.
A missing dependency or a broken install would mean clicking LabLink and
having *nothing happen at all*, with no way to find out why.

So this wrapper exists to make failure visible. It runs the requested target
and, if that raises before the GUI is up, writes the traceback to a log file
and puts it in front of the user in a message box.

The message box is drawn with ``ctypes`` against the Win32 API rather than
with Qt, deliberately: the most likely failure is that Qt itself did not
import, and an error reporter that needs the broken component cannot report
the breakage.

Usage (from the shortcuts, not by hand)::

    pythonw.exe lablink_launch.pyw client     # the GUI client
    pythonw.exe lablink_launch.pyw launcher   # setup/diagnostics launcher
    pythonw.exe lablink_launch.pyw server     # the API server
"""

import os
import runpy
import sys
import traceback
from datetime import datetime
from pathlib import Path

#: Repo root: this file lives at <root>/scripts/windows/.
ROOT = Path(__file__).resolve().parents[2]

#: What each shortcut asks for, and how that target is actually started.
#: The distinction matters: the client and server are packages started the way
#: `python -m` would start them, while the launcher is a script at the root.
TARGETS = {
    "client": ("module", "client.main"),
    "launcher": ("path", "lablink.py"),
    "server": ("module", "server.main"),
}

TITLE = "LabLink"


def log_path() -> Path:
    """Where a crash report goes.

    Under %LOCALAPPDATA% rather than the install directory, so it still works
    when LabLink is installed somewhere the user cannot write.
    """
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("TEMP") or "."
    directory = Path(base) / "LabLink"
    try:
        directory.mkdir(parents=True, exist_ok=True)
    except OSError:
        return Path(base) / "lablink-launch.log"
    return directory / "launch.log"


def show_error(message: str) -> None:
    """Put a message in front of the user without needing Qt or a console."""
    try:
        import ctypes

        # MB_ICONERROR | MB_SETFOREGROUND, so it cannot open behind everything.
        ctypes.windll.user32.MessageBoxW(None, message, TITLE, 0x10 | 0x10000)
    except Exception:
        # Not Windows, or user32 unavailable. The log below is then the only
        # record, which is better than losing the failure entirely.
        sys.stderr.write(message + "\n")


def report(target: str, error: BaseException) -> None:
    """Record a startup failure and tell the user where to look."""
    details = "".join(
        traceback.format_exception(type(error), error, error.__traceback__)
    )
    path = log_path()

    try:
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(
                f"\n{'=' * 70}\n{datetime.now().isoformat()} "
                f"starting {target!r} from {ROOT}\n{details}"
            )
        written = f"\n\nFull details were written to:\n{path}"
    except OSError:
        written = "\n\n(The log file could not be written.)"

    # The first line of the exception is the useful part for a lab user; the
    # traceback is for whoever they forward the log to.
    summary = f"{type(error).__name__}: {error}".strip()
    show_error(
        f"LabLink could not start {target}.\n\n{summary}{written}\n\n"
        f"Try the 'LabLink Launcher' shortcut, which checks the "
        f"installation and can repair missing dependencies."
    )


def main() -> int:
    target = (sys.argv[1] if len(sys.argv) > 1 else "client").lower()

    if target not in TARGETS:
        show_error(
            f"Unknown start target {target!r}.\n\n"
            f"Expected one of: {', '.join(sorted(TARGETS))}."
        )
        return 2

    kind, entry = TARGETS[target]

    # Run from the repo root. The server resolves `server.api` relative to the
    # working directory, and the client writes logs relative to it.
    os.chdir(ROOT)
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))

    # argv[0] should look like the program being run, not like this wrapper,
    # and the target's own argument parsing must not see our target name.
    sys.argv = [entry] + sys.argv[2:]

    try:
        if kind == "module":
            runpy.run_module(entry, run_name="__main__")
        else:
            runpy.run_path(str(ROOT / entry), run_name="__main__")
    except SystemExit as exit_request:
        # A clean exit, including argparse's --help path.
        return int(exit_request.code or 0)
    except BaseException as error:  # noqa: BLE001 - last line before silence
        report(target, error)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
