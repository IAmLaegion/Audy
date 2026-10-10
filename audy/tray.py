"""System tray icon and menu."""

from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from . import icons
from .engine import OFF, PAUSED, RUNNING, WAITING

PAUSE_CHOICES = [(15, "15 minutes"), (30, "30 minutes"), (60, "1 hour"), (120, "2 hours"), (240, "4 hours")]


class Tray(QSystemTrayIcon):
    def __init__(self, engine, on_open, on_quit, parent=None):
        super().__init__(parent)
        self.engine = engine
        self._state = None
        self._tip = ""

        menu = QMenu()
        self._status = QAction("", menu)
        self._status.setEnabled(False)
        menu.addAction(self._status)
        menu.addSeparator()
        self._toggle = menu.addAction("Start keepalive", engine.toggle)
        menu.addAction("Pulse now", engine.pulse_now)
        self._pause_menu = menu.addMenu("Pause for")
        for minutes, text in PAUSE_CHOICES:
            self._pause_menu.addAction(text, lambda m=minutes: engine.pause(m))
        self._resume = menu.addAction("Resume now", engine.resume)
        menu.addSeparator()
        menu.addAction("Open Audy", on_open)
        menu.addAction("Quit", on_quit)
        self.setContextMenu(menu)
        self._menu = menu

        self.activated.connect(
            lambda reason: on_open()
            if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick)
            else None
        )
        engine.changed.connect(self.refresh)
        self.refresh()

    def refresh(self):
        e = self.engine
        state = e.state
        if state != self._state:
            self._state = state
            self.setIcon(icons.tray_icon(state))
        self._toggle.setText("Stop keepalive" if e.active else "Start keepalive")
        self._resume.setVisible(state == PAUSED)
        self._pause_menu.menuAction().setVisible(state != PAUSED)

        if state == OFF:
            status = "Keepalive is off"
        elif state == PAUSED:
            status = f"Paused until {e.paused_until:%H:%M}"
        elif state == WAITING:
            status = f"Resting until {e.next_window_start():%H:%M}"
        else:
            left = e.seconds_until_next()
            status = "Next pulse in " + (f"{int(left) // 60}:{int(left) % 60:02d}" if left is not None else "…")
        self._status.setText(status)
        tip = f"Audy · {status}"
        if tip != self._tip:
            self._tip = tip
            self.setToolTip(tip)

    def tick(self):
        if self._state == RUNNING:
            self.refresh()
