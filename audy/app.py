"""Application bootstrap: single instance, wiring, startup behaviour."""

import os
import sys

from PySide6.QtCore import QTimer
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication, QSystemTrayIcon

from . import config, icons, platform_win, theme
from .engine import Engine
from .tray import Tray
from .window import MainWindow

INSTANCE_KEY = "Audy-single-instance"


def _signal_existing_instance():
    sock = QLocalSocket()
    sock.connectToServer(INSTANCE_KEY)
    if sock.waitForConnected(300):
        sock.write(b"show")
        sock.waitForBytesWritten(300)
        sock.disconnectFromServer()
        return True
    return False


def run(argv):
    platform_win.set_app_user_model_id()
    app = QApplication(argv)
    app.setApplicationName("Audy")
    app.setStyle("Fusion")
    app.setQuitOnLastWindowClosed(False)

    if _signal_existing_instance():
        return 0
    server = QLocalServer()
    QLocalServer.removeServer(INSTANCE_KEY)
    server.listen(INSTANCE_KEY)

    app.setWindowIcon(icons.app_icon())
    app.setFont(theme.font(13))
    app.setStyleSheet(theme.stylesheet())

    settings = config.load()
    first_run = not os.path.exists(config.CONFIG_PATH)
    if first_run and platform_win.remove_legacy_autostart():
        settings["start_with_windows"] = True
    if settings["start_with_windows"]:
        platform_win.set_autostart(True)  # keep the path current if the exe moved

    engine = Engine(settings)
    tray_ok = QSystemTrayIcon.isSystemTrayAvailable()
    window = MainWindow(engine, tray_ok)

    def quit_app():
        window.quitting = True
        engine.shutdown()
        config.save(engine.settings)
        tray.hide()
        app.quit()

    tray = Tray(engine, window.bring_to_front, quit_app)
    if tray_ok:
        tray.show()
    window._clock.timeout.connect(tray.tick)

    def hidden_hint():
        if not settings["tray_hint_shown"] and tray_ok:
            settings["tray_hint_shown"] = True
            config.save(settings)
            tray.showMessage(
                "Audy is still running",
                "Keepalive continues from the tray. Right-click the icon for options.",
                icons.app_icon(),
                4000,
            )

    window.on_hidden_to_tray = hidden_hint

    def on_connection():
        conn = server.nextPendingConnection()
        if conn:
            conn.readyRead.connect(lambda: (conn.readAll(), window.bring_to_front()))

    server.newConnection.connect(on_connection)

    launched_from_autostart = "--tray" in argv
    if settings["resume_on_launch"] and settings["was_running"]:
        QTimer.singleShot(600, engine.start)

    if not ((settings["start_minimized"] or launched_from_autostart) and tray_ok):
        window.show()

    config.save(settings)
    code = app.exec()
    engine.shutdown()
    return code


def main():
    sys.exit(run(sys.argv))
