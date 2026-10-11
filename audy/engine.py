"""The keepalive engine: decides when to pulse, where, and whether a pulse is needed at all."""

import time
from collections import deque
from datetime import datetime, timedelta
from datetime import time as dtime

from PySide6.QtCore import QObject, QTimer, Signal

from . import audio, config, platform_win

TICK_MS = 250
METER_EVERY_S = 0.5
RESCAN_EVERY_S = 60  # look for disconnected speakers coming back
RETRY_AFTER_S = 60  # wait before retrying a speaker that couldn't be reached
ACTIVITY_THRESHOLD = 0.003  # linear peak; our own pulse is suppressed separately
MAX_EVENTS = 60

OFF, RUNNING, PAUSED, WAITING = "off", "running", "paused", "waiting"


def _parse_hhmm(s):
    try:
        h, m = (int(x) for x in s.split(":"))
        return dtime(h % 24, m % 60)
    except Exception:
        return dtime(0, 0)


def short_name(name):
    """'Speakers (JBL CINEMA SB510)' -> 'JBL CINEMA SB510'."""
    if "(" in name and name.endswith(")"):
        inner = name[name.index("(") + 1 : -1].strip()
        if inner:
            return inner
    return name


def _friendly_error(err):
    e = err.lower()
    if "unavailable" in e or "invalid device" in e or "-9996" in e or "-9985" in e:
        return "busy or unavailable"
    if "sample rate" in e or "format" in e:
        return "unsupported format"
    return err


class Event:
    __slots__ = ("when", "kind", "text")

    def __init__(self, kind, text):
        self.when = datetime.now()
        self.kind = kind  # pulse | skip | error | info
        self.text = text


class Engine(QObject):
    changed = Signal()  # any state worth redrawing
    pulsed = Signal()  # a pulse actually went out
    event_added = Signal(object)
    _played = Signal(list, dict, bool)  # worker -> GUI thread

    def __init__(self, settings):
        super().__init__()
        self.settings = settings
        self.active = False
        self.paused_until = None
        self.events = deque(maxlen=MAX_EVENTS)
        self.pulses_today = 0
        self.skips_today = 0
        self._day = datetime.now().date()
        # Each speaker has its own silence timer: it gets a pulse once it has heard nothing
        # (no audio, no pulse) for a full interval. Timing from the last sound, not from the
        # last check, means a skipped pulse can't leave a speaker silent for two intervals.
        self._baseline = None  # treated as the last pulse for speakers not pulsed yet
        self._last_pulse = {}
        self._skip_noted = {}
        self._last_rescan = 0.0
        self._playing = False
        self._was_outside = False
        self._suppress_meter_until = 0.0
        self._last_meter = 0.0
        self._last_activity = {}
        self.targets = []  # resolved device names
        self.missing = []
        self.running_since = None

        self._meter = audio.LevelMeter()
        self._played.connect(self._on_played)
        self._timer = QTimer(self)
        self._timer.setInterval(TICK_MS)
        self._timer.timeout.connect(self._tick)
        self._timer.start()
        self.refresh_devices()

    # ------------------------------------------------------------ public API

    @property
    def interval_s(self):
        return max(1, int(self.settings["interval_minutes"])) * 60

    @property
    def state(self):
        if not self.active:
            return OFF
        if self.paused_until is not None:
            return PAUSED
        if not self._within_hours(datetime.now()):
            return WAITING
        return RUNNING

    @property
    def meter_available(self):
        return self._meter.available

    def _soonest(self):
        """(quiet_since, due_at) for the speaker that needs a pulse soonest, or None."""
        if self.state != RUNNING or self._baseline is None or not self.targets:
            return None
        return min(((self._quiet_since(n), self._due_at(n)) for n in self.targets), key=lambda x: x[1])

    def seconds_until_next(self):
        soonest = self._soonest()
        if soonest is None:
            return None
        return max(0.0, soonest[1] - time.monotonic())

    def cycle_progress(self):
        """0..1 through the current interval, for the dial's ring."""
        soonest = self._soonest()
        if soonest is None:
            return 0.0
        return min(1.0, max(0.0, (time.monotonic() - soonest[0]) / self.interval_s))

    def next_window_start(self):
        return _parse_hhmm(self.settings["active_from"])

    def start(self):
        if self.active:
            return
        self.active = True
        self.paused_until = None
        self.running_since = time.monotonic()
        self._was_outside = not self._within_hours(datetime.now())
        self._schedule(now=True)  # wake the speakers straight away, unless audio is already playing
        self._log("info", "Keepalive started")
        for name in self.missing:
            self._log("error", f"{short_name(name)} isn't connected")
        self._apply_keep_awake()
        self._persist_running()
        self.changed.emit()

    def stop(self):
        if not self.active:
            return
        self.active = False
        self.paused_until = None
        self.running_since = None
        self._baseline = None
        self._log("info", "Keepalive stopped")
        self._apply_keep_awake()
        self._persist_running()
        self.changed.emit()

    def toggle(self):
        self.stop() if self.active else self.start()

    def pause(self, minutes):
        if not self.active:
            self.start()
        self.paused_until = datetime.now() + timedelta(minutes=minutes)
        self._log("info", f"Paused until {self.paused_until:%H:%M}")
        self.changed.emit()

    def resume(self):
        if self.paused_until is None:
            return
        self.paused_until = None
        self._schedule(now=True)
        self._log("info", "Resumed")
        self.changed.emit()

    def pulse_now(self):
        """Send a pulse immediately, ignoring pause/hours (used as a test)."""
        if self._playing:
            return
        self._pulse(manual=True)

    def refresh_devices(self):
        if self._playing:
            return
        resolved, self.missing = audio.resolve(self.settings["devices"], rescan=True)
        self.targets = [d["name"] for d in resolved]
        self._meter.refresh()
        self.changed.emit()

    def apply_settings(self, settings, devices_changed=False, timing_changed=False):
        self.settings = settings
        if devices_changed:
            self.refresh_devices()
        # A new interval needs nothing here: due times are worked out from it on every tick.
        self._apply_keep_awake()
        self.changed.emit()

    def shutdown(self):
        self._timer.stop()
        platform_win.set_keep_awake(False)

    # ------------------------------------------------------------ internals

    def _within_hours(self, now):
        if not self.settings["active_hours_enabled"]:
            return True
        start = _parse_hhmm(self.settings["active_from"])
        end = _parse_hhmm(self.settings["active_to"])
        t = now.time()
        if start == end:
            return True
        if start < end:
            return start <= t < end
        return t >= start or t < end

    def _schedule(self, now=False):
        """Restart every speaker's timer: due immediately with now=True, else one interval from now."""
        m = time.monotonic()
        self._baseline = m - self.interval_s if now else m
        self._last_pulse = {}
        self._skip_noted = {}

    def _heard_audio(self):
        return self.settings["skip_when_playing"] and self._meter.available

    def _quiet_since(self, name):
        last = self._last_pulse.get(name, self._baseline)
        if self._heard_audio():
            last = max(last, self._last_activity.get(name, -1e9))
        return last

    def _due_at(self, name):
        return self._quiet_since(name) + self.interval_s

    def _note_skips(self, m):
        """Log once each time audio that was already playing pushed a speaker's pulse back."""
        if not self._heard_audio():
            return
        held = []
        for name in self.targets:
            pulsed = self._last_pulse.get(name, self._baseline)
            if pulsed + self.interval_s <= m < self._due_at(name) and self._skip_noted.get(name) != pulsed:
                self._skip_noted[name] = pulsed
                held.append(name)
        if held:
            self._log("skip", f"Skipped {', '.join(short_name(n) for n in held)}: audio already playing")
            self.skips_today += 1
            self.changed.emit()

    def _apply_keep_awake(self):
        platform_win.set_keep_awake(self.active and self.settings["keep_pc_awake"])

    def _persist_running(self):
        self.settings["was_running"] = self.active
        try:
            config.save(self.settings)
        except OSError:
            pass

    def _log(self, kind, text):
        ev = Event(kind, text)
        self.events.appendleft(ev)
        self.event_added.emit(ev)

    def _roll_day(self):
        today = datetime.now().date()
        if today != self._day:
            self._day = today
            self.pulses_today = 0
            self.skips_today = 0

    def _poll_meter(self, m):
        if not self._meter.available or m < self._suppress_meter_until:
            return
        for name in self.targets:
            peak = self._meter.peak(name)
            if peak is not None and peak > ACTIVITY_THRESHOLD:
                self._last_activity[name] = m

    def _tick(self):
        m = time.monotonic()
        if m - self._last_meter >= METER_EVERY_S:
            self._last_meter = m
            self._poll_meter(m)

        if not self.active:
            return
        self._roll_day()
        now = datetime.now()

        if self.paused_until is not None:
            if now >= self.paused_until:
                self.resume()
            return

        outside = not self._within_hours(now)
        if outside != self._was_outside:
            self._was_outside = outside
            if outside:
                self._log("info", "Outside active hours, letting speakers sleep")
            else:
                self._log("info", "Active hours started")
                self._schedule(now=True)
            self.changed.emit()
        if outside:
            return

        if self._playing:
            return
        if self.missing and m - self._last_rescan >= RESCAN_EVERY_S:
            self._last_rescan = m
            self.refresh_devices()
        self._note_skips(m)
        if any(m >= self._due_at(n) for n in self.targets):
            self._pulse(manual=False)

    def _pulse(self, manual):
        m = time.monotonic()
        self._last_rescan = m
        previously_missing = set(self.missing)
        resolved, self.missing = audio.resolve(self.settings["devices"], rescan=True)
        self.targets = [d["name"] for d in resolved]
        self._meter.refresh()

        for name in self.missing:
            if manual or name not in previously_missing:
                self._log("error", f"{short_name(name)} isn't connected")

        if manual or self._baseline is None:
            to_play = resolved  # a test pulse goes everywhere
        else:
            to_play = [d for d in resolved if m >= self._due_at(d["name"])]

        if not to_play:
            self.changed.emit()
            return

        s = self.settings
        wave, freq = audio.signal_params(s)
        self._playing = True
        self._suppress_meter_until = m + s["duration_s"] + 1.5
        self.pulsed.emit()
        self.changed.emit()
        audio.play(
            to_play,
            wave,
            freq,
            s["level_db"],
            s["duration_s"],
            lambda ok, errors: self._played.emit(ok, errors, manual),
        )

    def _on_played(self, ok, errors, manual):
        self._playing = False
        m = time.monotonic()
        for name in ok:
            self._last_pulse[name] = m
        for name in errors:
            # Try again in a minute rather than on every tick.
            self._last_pulse[name] = m - self.interval_s + RETRY_AFTER_S
        if ok:
            names = ", ".join(short_name(n) for n in ok)
            self._log("pulse", f"{'Test pulse' if manual else 'Pulse'} sent to {names}")
            if not manual:
                self.pulses_today += 1
        for name, err in errors.items():
            self._log("error", f"Couldn't reach {short_name(name)}: {_friendly_error(err)}")
        self.changed.emit()
