"""Persistent settings, stored as JSON in %APPDATA%\\Audy."""

import json
import os

APP_DIR = os.path.join(os.getenv("APPDATA") or os.path.expanduser("~"), "Audy")
CONFIG_PATH = os.path.join(APP_DIR, "settings.json")
LEGACY_CONFIG_PATH = os.path.join(
    os.getenv("APPDATA") or os.path.expanduser("~"), "StandbyPreventer", "config.json"
)

# Signal presets: (frequency Hz, waveform). "noise" ignores frequency.
SIGNAL_PRESETS = {
    "ultrasonic": {"label": "Ultrasonic", "frequency": 18000, "wave": "sine"},
    "subsonic": {"label": "Sub-bass", "frequency": 20, "wave": "sine"},
    "noise": {"label": "Low noise", "frequency": 0, "wave": "noise"},
    "custom": {"label": "Custom", "frequency": 1000, "wave": "sine"},
}

DEFAULT_DEVICE = "__default__"

DEFAULTS = {
    # Keepalive
    "devices": [DEFAULT_DEVICE],
    "interval_minutes": 9,
    "signal": "ultrasonic",
    "custom_frequency": 1000,
    "level_db": -42,
    "duration_s": 1.0,
    # Smart behaviour
    "skip_when_playing": True,
    "active_hours_enabled": False,
    "active_from": "08:00",
    "active_to": "23:00",
    # App
    "start_with_windows": False,
    "start_minimized": False,
    "close_to_tray": True,
    "keep_pc_awake": False,
    "resume_on_launch": True,
    "was_running": False,
    "tray_hint_shown": False,
}


def _migrate_legacy():
    """Carry over settings from the old Standby Preventer app, if present."""
    try:
        with open(LEGACY_CONFIG_PATH, "r") as f:
            old = json.load(f)
    except Exception:
        return {}
    migrated = {}
    if isinstance(old.get("interval_minutes"), int):
        migrated["interval_minutes"] = max(1, min(60, old["interval_minutes"]))
    if "start_with_windows" in old:
        migrated["start_with_windows"] = bool(old["start_with_windows"])
    if "minimize_to_tray" in old:
        migrated["close_to_tray"] = bool(old["minimize_to_tray"])
    return migrated


def load():
    if not os.path.exists(CONFIG_PATH):
        return {**DEFAULTS, **_migrate_legacy()}
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        merged = {**DEFAULTS, **{k: v for k, v in data.items() if k in DEFAULTS}}
        if not merged["devices"]:
            merged["devices"] = [DEFAULT_DEVICE]
        if merged["signal"] not in SIGNAL_PRESETS:
            merged["signal"] = DEFAULTS["signal"]
        return merged
    except Exception:
        return dict(DEFAULTS)


def save(settings):
    os.makedirs(APP_DIR, exist_ok=True)
    tmp = CONFIG_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2)
    os.replace(tmp, CONFIG_PATH)
