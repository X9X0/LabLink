"""Running helper processes without flashing a console window.

On Windows a GUI process launched from ``pythonw.exe`` has no console, so
every ``subprocess`` call that starts a console program creates one -- and it
appears on screen. One at startup is a blink; a dialog polling once a second
is a strobe, and it makes the whole client look broken.

``CREATE_NO_WINDOW`` suppresses it. Everything here is a no-op off Windows.
"""

from __future__ import annotations

import subprocess
import sys

CREATE_NO_WINDOW = 0x08000000


def no_window_kwargs() -> dict:
    """Keyword arguments that keep a child process off the screen.

    Spread into ``subprocess.run``/``Popen``::

        subprocess.run(cmd, capture_output=True, **no_window_kwargs())
    """
    if not sys.platform.startswith("win"):
        return {}

    # Both, because they cover different cases: the flag stops a console being
    # allocated at all, and STARTF_USESHOWWINDOW hides one that a program
    # creates for itself anyway.
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = subprocess.SW_HIDE

    return {"creationflags": CREATE_NO_WINDOW, "startupinfo": startupinfo}
