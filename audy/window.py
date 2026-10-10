"""Main window: a home screen with the dial, and a settings screen."""

import math
import time

from PySide6.QtCore import QEasingCurve, QParallelAnimationGroup, QPoint, QPropertyAnimation, Qt, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QScrollArea,
    QSlider,
    QComboBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from . import __version__, audio, config, icons, platform_win, theme
from .engine import OFF, PAUSED, RUNNING, WAITING, short_name
from .theme import Icon
from .tray import PAUSE_CHOICES
from .widgets import (
    ElidedLabel,
    EventDot,
    PowerDial,
    Segmented,
    SettingRow,
    Spark,
    ToggleSwitch,
    card,
    divider,
    icon_button,
    label,
    section_label,
)

SIGNAL_HINTS = {
    "ultrasonic": "An 18 kHz tone, above what most people can hear. Works with most speakers and soundbars.",
    "subsonic": "A 20 Hz tone, below hearing for most setups. Try this if your speaker filters out high frequencies.",
    "noise": "Very quiet broadband noise. Good for digital inputs (optical, HDMI) that wake on any signal.",
    "custom": "Pick your own frequency.",
}


def _join_names(names):
    names = [short_name(n) for n in names]
    if not names:
        return "no devices"
    if len(names) == 1:
        return names[0]
    if len(names) == 2:
        return f"{names[0]} and {names[1]}"
    return f"{len(names)} devices"


def _device_kind(name):
    """'Speakers (JBL CINEMA SB510)' -> 'Speakers'."""
    if "(" in name and name.endswith(")"):
        return name[: name.index("(")].strip() or None
    return None


def _fmt_duration(seconds):
    m = int(seconds // 60)
    if m < 60:
        return f"{m}m"
    return f"{m // 60}h {m % 60:02d}m"


def _freq_to_slider(f):
    return int(round(1000 * math.log(max(20, f) / 20) / math.log(1000)))


def _slider_to_freq(v):
    f = 20 * (1000 ** (v / 1000))
    return int(round(f, -1 if f >= 1000 else 0))


def _fmt_freq(f):
    return f"{f / 1000:.1f} kHz" if f >= 1000 else f"{f} Hz"


def _scroll(widget):
    sc = QScrollArea()
    sc.setWidgetResizable(True)
    sc.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    sc.setFrameShape(QScrollArea.Shape.NoFrame)
    sc.setWidget(widget)
    return sc


# ================================================================ home


class HomePage(QWidget):
    def __init__(self, engine, open_settings):
        super().__init__()
        self.setObjectName("page")
        self.engine = engine

        body = QWidget()
        body.setObjectName("page")
        lay = QVBoxLayout(body)
        lay.setContentsMargins(20, 14, 20, 20)
        lay.setSpacing(0)

        # Header
        head = QHBoxLayout()
        logo = QLabel()
        logo.setPixmap(icons.app_pixmap(56).scaled(28, 28, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        head.addWidget(logo)
        head.addSpacing(8)
        head.addWidget(label("Audy", 17, QFont.Weight.DemiBold))
        head.addStretch(1)
        gear = icon_button(Icon.SETTINGS, tooltip="Settings")
        gear.clicked.connect(open_settings)
        head.addWidget(gear)
        lay.addLayout(head)
        lay.addSpacing(4)

        # Dial
        self.dial = PowerDial()
        self.dial.clicked.connect(engine.toggle)
        lay.addWidget(self.dial, 0, Qt.AlignmentFlag.AlignHCenter)

        # Status
        self.headline = label("", 15, QFont.Weight.DemiBold)
        self.headline.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.headline.setWordWrap(True)
        self.detail = label("", 12, role="muted")
        self.detail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.detail.setWordWrap(True)
        lay.addWidget(self.headline)
        lay.addSpacing(3)
        lay.addWidget(self.detail)
        lay.addSpacing(16)

        # Actions
        actions = QHBoxLayout()
        actions.setSpacing(10)
        self.pulse_btn = QPushButton("Pulse now")
        self.pulse_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.pulse_btn.setToolTip("Send a keepalive pulse right away")
        self.pulse_btn.clicked.connect(engine.pulse_now)
        self.pause_btn = QPushButton("Pause")
        self.pause_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._pause_menu = QMenu(self)
        for minutes, text in PAUSE_CHOICES:
            self._pause_menu.addAction(f"For {text}", lambda m=minutes: engine.pause(m))
        self.pause_btn.clicked.connect(self._pause_clicked)
        for b in (self.pulse_btn, self.pause_btn):
            b.setMinimumHeight(38)
            actions.addWidget(b, 1)
        lay.addLayout(actions)
        lay.addSpacing(18)

        # Today
        lay.addWidget(section_label("Today"))
        lay.addSpacing(8)
        today, tl = card()
        tl.setContentsMargins(16, 14, 16, 14)
        stats = QHBoxLayout()
        stats.setSpacing(0)
        self.stat_pulses = self._stat(stats, "pulses")
        self.stat_skips = self._stat(stats, "skipped")
        self.stat_uptime = self._stat(stats, "on for")
        tl.addLayout(stats)
        tl.addSpacing(12)
        self.spark = Spark()
        tl.addWidget(self.spark)
        lay.addWidget(today)
        lay.addSpacing(18)

        # Activity
        lay.addWidget(section_label("Activity"))
        lay.addSpacing(8)
        act, self._act_lay = card()
        self._act_lay.setContentsMargins(16, 4, 16, 4)
        lay.addWidget(act)
        lay.addStretch(1)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(_scroll(body))

        engine.changed.connect(self.refresh)
        engine.event_added.connect(lambda _e: self._rebuild_activity())
        engine.pulsed.connect(self.dial.pulse)
        self._rebuild_activity()
        self.refresh()

    def _stat(self, row, caption):
        col = QVBoxLayout()
        col.setSpacing(0)
        value = label("0", 22, QFont.Weight.DemiBold)
        col.addWidget(value)
        col.addWidget(label(caption, 12, role="muted"))
        row.addLayout(col, 1)
        return value

    def _pause_clicked(self):
        if self.engine.state == PAUSED:
            self.engine.resume()
        else:
            self._pause_menu.popup(self.pause_btn.mapToGlobal(QPoint(0, self.pause_btn.height() + 4)))

    def _rebuild_activity(self):
        while self._act_lay.count():
            item = self._act_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        events = list(self.engine.events)[:4]
        if not events:
            empty = label("Nothing yet. Pulses and skips will show up here.", 12, role="muted")
            empty.setContentsMargins(0, 12, 0, 12)
            self._act_lay.addWidget(empty)
        colors = {"pulse": theme.ACCENT, "skip": theme.SKY, "error": theme.RED, "info": theme.FAINT}
        for i, ev in enumerate(events):
            if i:
                self._act_lay.addWidget(divider())
            row = QWidget()
            rl = QHBoxLayout(row)
            rl.setContentsMargins(0, 10, 0, 10)
            rl.setSpacing(10)
            rl.addWidget(EventDot(colors.get(ev.kind, theme.FAINT)), 0, Qt.AlignmentFlag.AlignVCenter)
            rl.addWidget(ElidedLabel(ev.text, 12), 1)
            rl.addWidget(label(f"{ev.when:%H:%M}", 12, role="faint"))
            self._act_lay.addWidget(row)
        kinds = [ev.kind for ev in reversed(self.engine.events) if ev.kind in ("pulse", "skip", "error")]
        self.spark.set_bars(kinds)

    def refresh(self):
        e = self.engine
        state = e.state
        s = e.settings
        signal = config.SIGNAL_PRESETS[s["signal"]]["label"]

        if state == RUNNING:
            left = e.seconds_until_next()
            title = f"{int(left) // 60}:{int(left) % 60:02d}" if left is not None else "…"
            self.dial.set_state(state, title, "until next pulse", e.cycle_progress())
            self.headline.setText(f"Keeping {_join_names(e.targets)} awake")
            self.detail.setText(f"{signal} pulse every {s['interval_minutes']} min")
        elif state == PAUSED:
            self.dial.set_state(state, "Paused", f"until {e.paused_until:%H:%M}", 1.0)
            self.headline.setText("Paused")
            self.detail.setText(f"Picks back up at {e.paused_until:%H:%M}")
        elif state == WAITING:
            start = e.next_window_start()
            self.dial.set_state(state, "Resting", f"until {start:%H:%M}", 1.0)
            self.headline.setText("Outside active hours")
            self.detail.setText(f"Your speakers can sleep. Back on at {start:%H:%M}.")
        else:
            self.dial.set_state(OFF, "Off", "Tap to start", 0.0)
            self.headline.setText("Keepalive is off")
            self.detail.setText("Your speakers may drift into standby.")

        if e.missing:
            names = ", ".join(short_name(n) for n in e.missing)
            self.detail.setText(f"<span style='color:{theme.RED}'>{names} not connected</span>")

        self.pause_btn.setText("Resume" if state == PAUSED else "Pause")
        self.pause_btn.setEnabled(state != OFF)

        self.stat_pulses.setText(str(e.pulses_today))
        self.stat_skips.setText(str(e.skips_today))
        self.stat_uptime.setText(_fmt_duration(time.monotonic() - e.running_since) if e.running_since else "–")

    def tick(self):
        if self.engine.state == RUNNING or self.engine.running_since:
            self.refresh()


# ================================================================ settings


class SettingsPage(QWidget):
    def __init__(self, engine, go_back, on_change):
        super().__init__()
        self.setObjectName("page")
        self.engine = engine
        self.s = engine.settings
        self._on_change = on_change

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        head = QHBoxLayout()
        head.setContentsMargins(12, 14, 20, 8)
        back = icon_button(Icon.BACK, tooltip="Back")
        back.clicked.connect(go_back)
        head.addWidget(back)
        head.addSpacing(4)
        head.addWidget(label("Settings", 17, QFont.Weight.DemiBold))
        head.addStretch(1)
        outer.addLayout(head)

        body = QWidget()
        body.setObjectName("page")
        lay = QVBoxLayout(body)
        lay.setContentsMargins(20, 8, 20, 24)
        lay.setSpacing(0)
        self._lay = lay

        self._build_output()
        self._build_signal()
        self._build_timing()
        self._build_smart()
        self._build_system()

        foot = label(f"Audy {__version__}  ·  Settings live in %APPDATA%\\Audy", 11, role="faint")
        foot.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addSpacing(6)
        lay.addWidget(foot)
        lay.addStretch(1)
        outer.addWidget(_scroll(body), 1)

    # ---------------------------------------------------- helpers

    def _section(self, title, trailing=None):
        row = QHBoxLayout()
        row.addWidget(section_label(title))
        row.addStretch(1)
        if trailing:
            row.addWidget(trailing)
        self._lay.addLayout(row)
        self._lay.addSpacing(8)
        frame, cl = card()
        self._lay.addWidget(frame)
        self._lay.addSpacing(22)
        return cl

    def _rows(self, cl, rows):
        for i, r in enumerate(rows):
            if i:
                cl.addWidget(divider())
            cl.addWidget(r)

    def _toggle_row(self, title, desc, key, after=None):
        t = ToggleSwitch(self.s[key])

        def changed(v):
            self.s[key] = v
            if after:
                after(v)
            self._on_change()

        t.toggled.connect(changed)
        return SettingRow(title, desc, t), t

    def _slider_block(self, title, lo, hi, value, fmt, on_value, hint=None):
        w = QWidget()
        l = QVBoxLayout(w)
        l.setContentsMargins(0, 12, 0, 12)
        l.setSpacing(6)
        top = QHBoxLayout()
        top.addWidget(label(title, 13, QFont.Weight.Medium))
        top.addStretch(1)
        val = label("", 13, QFont.Weight.DemiBold)
        top.addWidget(val)
        l.addLayout(top)
        sl = QSlider(Qt.Orientation.Horizontal)
        sl.setRange(lo, hi)
        sl.setValue(value)
        sl.setCursor(Qt.CursorShape.PointingHandCursor)
        val.setText(fmt(value))

        def changed(v):
            val.setText(fmt(v))
            on_value(v)

        sl.valueChanged.connect(changed)
        l.addWidget(sl)
        if hint:
            h = label(hint, 12, role="muted")
            h.setWordWrap(True)
            l.addWidget(h)
        return w, sl

    # ---------------------------------------------------- sections

    def _build_output(self):
        refresh = icon_button(Icon.REFRESH, size=26, glyph_px=12, tooltip="Rescan devices")
        refresh.clicked.connect(self._rebuild_devices)
        self._dev_lay = self._section("Output devices", refresh)
        self._rebuild_devices()

    def _rebuild_devices(self):
        while self._dev_lay.count():
            item = self._dev_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        devices = audio.list_output_devices(rescan=not self.engine._playing)
        default = audio.default_output_name()
        selected = set(self.s["devices"])
        rows = []
        self._dev_toggles = {}

        entries = [(config.DEFAULT_DEVICE, "System default", short_name(default) if default else "None")]
        for d in devices:
            entries.append((d["name"], short_name(d["name"]), _device_kind(d["name"])))
        # Keep selected-but-unplugged devices visible so they can be unticked.
        known = {d["name"] for d in devices}
        for name in self.s["devices"]:
            if name != config.DEFAULT_DEVICE and name not in known:
                entries.append((name, short_name(name), "Not connected"))

        for key, title, desc in entries:
            t = ToggleSwitch(key in selected)
            t.toggled.connect(lambda on, k=key: self._device_toggled(k, on))
            self._dev_toggles[key] = t
            rows.append(SettingRow(title, desc, t))
        self._rows(self._dev_lay, rows)
        self.engine.refresh_devices()

    def _device_toggled(self, key, on):
        devs = [d for d in self.s["devices"] if d != key]
        if on:
            devs.append(key)
        if not devs:
            # Never leave Audy with nothing to keep awake.
            devs = [config.DEFAULT_DEVICE]
            t = self._dev_toggles.get(config.DEFAULT_DEVICE)
            if t and not t.isChecked():
                t.blockSignals(True)
                t.setChecked(True)
                t.set_knob(1.0)
                t.blockSignals(False)
        self.s["devices"] = devs
        self._on_change(devices=True)

    def _build_signal(self):
        cl = self._section("Signal")
        seg_wrap = QWidget()
        sw = QVBoxLayout(seg_wrap)
        sw.setContentsMargins(0, 14, 0, 4)
        sw.setSpacing(10)
        seg = Segmented([(k, v["label"]) for k, v in config.SIGNAL_PRESETS.items()], self.s["signal"])
        sw.addWidget(seg)
        self._signal_hint = label(SIGNAL_HINTS[self.s["signal"]], 12, role="muted")
        self._signal_hint.setWordWrap(True)
        sw.addWidget(self._signal_hint)
        cl.addWidget(seg_wrap)

        def set_freq(v):
            self.s["custom_frequency"] = _slider_to_freq(v)
            self._on_change()

        self._freq_block, _ = self._slider_block(
            "Frequency",
            0,
            1000,
            _freq_to_slider(self.s["custom_frequency"]),
            lambda v: _fmt_freq(_slider_to_freq(v)),
            set_freq,
        )
        cl.addWidget(self._freq_block)
        self._freq_block.setVisible(self.s["signal"] == "custom")

        def on_signal(key):
            self.s["signal"] = key
            self._signal_hint.setText(SIGNAL_HINTS[key])
            self._freq_block.setVisible(key == "custom")
            self._on_change()

        seg.changed.connect(on_signal)

        cl.addWidget(divider())

        def set_level(v):
            self.s["level_db"] = v
            self._on_change()

        lvl, _ = self._slider_block(
            "Level", -70, -20, int(self.s["level_db"]), lambda v: f"{v} dB", set_level,
            "Louder is more reliable but may become audible on some setups.",
        )
        cl.addWidget(lvl)
        cl.addWidget(divider())

        def set_dur(v):
            self.s["duration_s"] = v / 10
            self._on_change()

        dur, _ = self._slider_block(
            "Pulse length", 2, 50, int(round(self.s["duration_s"] * 10)), lambda v: f"{v / 10:.1f} s", set_dur
        )
        cl.addWidget(dur)
        cl.addWidget(divider())

        test = QPushButton("Send a test pulse")
        test.setCursor(Qt.CursorShape.PointingHandCursor)
        test.clicked.connect(self.engine.pulse_now)
        wrap = QWidget()
        wl = QHBoxLayout(wrap)
        wl.setContentsMargins(0, 12, 0, 12)
        hint = label("Watch your speaker's standby light while it plays.", 12, role="muted")
        hint.setWordWrap(True)
        wl.addWidget(hint, 1)
        wl.addWidget(test)
        cl.addWidget(wrap)

    def _build_timing(self):
        cl = self._section("Timing")

        def set_interval(v):
            self.s["interval_minutes"] = v
            self._on_change(timing=True)

        block, _ = self._slider_block(
            "Pulse every", 1, 60, int(self.s["interval_minutes"]), lambda v: f"{v} min", set_interval,
            "Most speakers sleep after 10 to 20 minutes of silence. Pick something a little shorter.",
        )
        cl.addWidget(block)

    def _build_smart(self):
        cl = self._section("Smart")
        skip_row, _ = self._toggle_row(
            "Skip when audio is playing",
            "Don't pulse a device that's already playing something."
            + ("" if self.engine.meter_available else " (Unavailable: audio meter couldn't load.)"),
            "skip_when_playing",
        )

        hours_row, hours_toggle = self._toggle_row(
            "Active hours",
            "Only keep speakers awake during these hours, so they can sleep overnight.",
            "active_hours_enabled",
            after=lambda v: self._set_hours_enabled(v),
        )

        times = QWidget()
        tl = QHBoxLayout(times)
        tl.setContentsMargins(0, 0, 0, 14)
        tl.setSpacing(8)
        self._from = self._time_edit("active_from")
        self._to = self._time_edit("active_to")
        tl.addWidget(label("From", 12, role="muted"))
        tl.addWidget(self._from)
        tl.addSpacing(6)
        tl.addWidget(label("to", 12, role="muted"))
        tl.addWidget(self._to)
        tl.addStretch(1)

        cl.addWidget(skip_row)
        cl.addWidget(divider())
        cl.addWidget(hours_row)
        cl.addWidget(times)
        self._set_hours_enabled(self.s["active_hours_enabled"])

    def _time_edit(self, key):
        box = QComboBox()
        box.setCursor(Qt.CursorShape.PointingHandCursor)
        slots = [f"{h:02d}:{m:02d}" for h in range(24) for m in (0, 30)]
        if self.s[key] not in slots:
            slots.append(self.s[key])
            slots.sort()
        box.addItems(slots)
        box.setCurrentText(self.s[key])
        box.setMaxVisibleItems(10)

        def changed(text):
            self.s[key] = text
            self._on_change()

        box.currentTextChanged.connect(changed)
        return box

    def _set_hours_enabled(self, on):
        self._from.setEnabled(on)
        self._to.setEnabled(on)

    def _build_system(self):
        cl = self._section("System")
        rows = [
            self._toggle_row(
                "Start with Windows", "Launch quietly into the tray when you sign in.", "start_with_windows",
                after=platform_win.set_autostart,
            )[0],
            self._toggle_row(
                "Resume on launch", "If keepalive was on when Audy closed, turn it back on.", "resume_on_launch"
            )[0],
            self._toggle_row("Start in the tray", "Don't show the window when Audy opens.", "start_minimized")[0],
            self._toggle_row("Close to tray", "The close button hides Audy instead of quitting.", "close_to_tray")[0],
            self._toggle_row(
                "Keep PC awake", "Stop Windows from sleeping while keepalive is on.", "keep_pc_awake"
            )[0],
        ]
        self._rows(cl, rows)


# ================================================================ window


class MainWindow(QWidget):
    def __init__(self, engine, tray_available):
        super().__init__()
        self.setObjectName("root")
        self.engine = engine
        self.tray_available = tray_available
        self.quitting = False
        self.setWindowTitle("Audy")
        self.setWindowIcon(icons.app_icon())
        self.setFixedWidth(420)
        self.setMinimumHeight(560)
        self.resize(420, 700)

        self._save_timer = QTimer(self, singleShot=True, interval=400)
        self._save_timer.timeout.connect(lambda: config.save(engine.settings))
        self._pending = {"devices": False, "timing": False}

        self.stack = QStackedWidget()
        self.home = HomePage(engine, lambda: self.slide_to(1))
        self.settings_page = SettingsPage(engine, lambda: self.slide_to(0), self._settings_changed)
        self.stack.addWidget(self.home)
        self.stack.addWidget(self.settings_page)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.stack)

        self._clock = QTimer(self, interval=500)
        self._clock.timeout.connect(self.home.tick)
        self._clock.start()
        self._anim = None

    def showEvent(self, e):
        super().showEvent(e)
        platform_win.style_title_bar(self.winId(), theme.rgb(theme.BG), theme.rgb(theme.TEXT), theme.rgb(theme.BORDER))

    def _settings_changed(self, devices=False, timing=False):
        self.engine.apply_settings(self.engine.settings, devices_changed=devices, timing_changed=timing)
        self._save_timer.start()

    def slide_to(self, index):
        if index == self.stack.currentIndex() or (self._anim and self._anim.state() == QPropertyAnimation.State.Running):
            return
        old = self.stack.currentWidget()
        new = self.stack.widget(index)
        w = self.stack.width()
        direction = 1 if index > self.stack.currentIndex() else -1
        new.setGeometry(0, 0, w, self.stack.height())
        new.move(direction * w, 0)
        new.show()
        new.raise_()

        group = QParallelAnimationGroup(self)
        for widget, start, end in ((old, QPoint(0, 0), QPoint(-direction * w // 3, 0)), (new, QPoint(direction * w, 0), QPoint(0, 0))):
            a = QPropertyAnimation(widget, b"pos", group)
            a.setDuration(260)
            a.setEasingCurve(QEasingCurve.Type.OutCubic)
            a.setStartValue(start)
            a.setEndValue(end)
            group.addAnimation(a)

        def done():
            self.stack.setCurrentIndex(index)
            old.move(0, 0)

        group.finished.connect(done)
        self._anim = group
        group.start()

    def bring_to_front(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def closeEvent(self, e):
        if not self.quitting and self.engine.settings["close_to_tray"] and self.tray_available:
            e.ignore()
            self.hide()
            self.on_hidden_to_tray()
            return
        e.accept()

    def on_hidden_to_tray(self):
        pass  # replaced by the app to show a one-time tray hint
