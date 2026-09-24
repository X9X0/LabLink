"""Showing a modal from inside a coroutine, without wedging the loop.

A Qt modal runs a nested event loop, and qasync pumps asyncio from it.
So a dialog opened *inside* a coroutine lets that nested loop try to
step other asyncio tasks while this one is still the current task, and
asyncio refuses::

    RuntimeError: Cannot enter into task <EquipmentPanel.refresh()>
      while another task <EquipmentPanel.connect_equipment()
      running at equipment_panel.py:924> is being executed

Line 924 was ``QMessageBox.information(... "Equipment connected
successfully")``. The refresh it blocked had already finished its
fan-out and could never be resumed to use it; its in-flight slot then
stayed held until the 45s backstop, and every refresh in between was
refused. Two of those stalls lasted 310s and 177s -- a dialog left open
that long. A timeout around the fetch could not save it either, because
the timer callback has to step the same blocked task.

Both helpers here show the dialog from a zero-delay timer instead, by
which time the calling coroutine has either finished or suspended and
is nobody's current task, leaving the nested loop free to run
everything else.

Extracted from EquipmentPanel, which found this the hard way, so that
the panels converted later do not have to find it again.
"""

import asyncio

from PyQt6.QtCore import QTimer


def say_later(parent, show, title: str, text: str) -> None:
    """Put up a dialog that needs no answer, on the next pass of the loop.

    Args:
        parent: the widget to parent the dialog to.
        show: the QMessageBox class method, e.g. QMessageBox.information.
        title: dialog title.
        text: dialog body.
    """
    QTimer.singleShot(0, lambda: show(parent, title, text))


async def ask(put_it_up):
    """Run a modal that has an answer, without blocking the loop.

    A prompt cannot simply be deferred like :func:`say_later` -- the
    caller needs what the operator chose. Showing it from a timer and
    awaiting the answer gets both: while the coroutine waits on the
    future it is suspended and is nobody's current task, so the nested
    Qt loop is free to run everything else.

    Args:
        put_it_up: called on the Qt thread; returns the operator's answer.

    Returns:
        Whatever ``put_it_up`` returned.
    """
    answer = asyncio.get_running_loop().create_future()

    def show():
        if answer.done():           # the widget went away meanwhile
            return
        try:
            answer.set_result(put_it_up())
        except Exception as e:      # a dialog that cannot even open
            answer.set_exception(e)

    QTimer.singleShot(0, show)
    return await answer
