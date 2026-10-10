"""Small Windows integrations: dark title bar, keep-awake, autostart, taskbar identity."""

import ctypes
import os
import sys
import winreg

APP_ID = "Audy.Keepalive"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_NAME = "Audy"
LEGACY_RUN_NAME = "StandbyPreventer"

ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001


def set_app_user_model_id():
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
    except Exception:
        pass


def style_title_bar(hwnd, caption_rgb, text_rgb, border_rgb):
    """Dark-mode title bar tinted to match the window background (Windows 11)."""
    try:
        dwm = ctypes.windll.dwmapi
        hwnd = ctypes.c_void_p(int(hwnd))

        def set_attr(attr, value):
            v = ctypes.c_int(value)
            dwm.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(v), ctypes.sizeof(v))

        def colorref(rgb):
            r, g, b = rgb
            return r | (g << 8) | (b << 16)

        set_attr(20, 1)  # DWMWA_USE_IMMERSIVE_DARK_MODE
        set_attr(34, colorref(border_rgb))  # DWMWA_BORDER_COLOR
        set_attr(35, colorref(caption_rgb))  # DWMWA_CAPTION_COLOR
        set_attr(36, colorref(text_rgb))  # DWMWA_TEXT_COLOR
    except Exception:
        pass


def set_keep_awake(enabled):
    """Stop the PC from sleeping while enabled. Must be called from the GUI thread."""
    try:
        flags = ES_CONTINUOUS | (ES_SYSTEM_REQUIRED if enabled else 0)
        ctypes.windll.kernel32.SetThreadExecutionState(flags)
    except Exception:
        pass


# ---------------------------------------------------------------- autostart


def _launch_command():
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" --tray'
    pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    exe = pythonw if os.path.exists(pythonw) else sys.executable
    main = os.path.abspath(sys.argv[0])
    return f'"{exe}" "{main}" --tray'


def set_autostart(enabled):
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            if enabled:
                winreg.SetValueEx(key, RUN_NAME, 0, winreg.REG_SZ, _launch_command())
            else:
                try:
                    winreg.DeleteValue(key, RUN_NAME)
                except FileNotFoundError:
                    pass
        return True
    except OSError:
        return False


def remove_legacy_autostart():
    """Drop the old Standby Preventer Run entry. Returns True if one existed."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_ALL_ACCESS) as key:
            winreg.QueryValueEx(key, LEGACY_RUN_NAME)
            winreg.DeleteValue(key, LEGACY_RUN_NAME)
            return True
    except OSError:
        return False
