"""Audio output: device discovery, keepalive signal synthesis, playback and level metering."""

import threading

import numpy as np
import sounddevice as sd

from . import config

FADE_S = 0.03  # raised-cosine fade so the pulse never clicks


# ---------------------------------------------------------------- devices


def _wasapi_index():
    for i, api in enumerate(sd.query_hostapis()):
        if "WASAPI" in api["name"]:
            return i
    return None


def list_output_devices(rescan=False):
    """Return [{'name', 'index', 'samplerate', 'channels'}] for WASAPI outputs.

    WASAPI is used because it reports full, stable endpoint names (MME truncates
    them to 31 chars) that match what the Windows sound settings show.
    """
    if rescan:
        # PortAudio only enumerates devices at init; reinitialise to see hot-plugged ones.
        # Never call this while a stream is open.
        try:
            sd._terminate()
            sd._initialize()
        except Exception:
            pass
    api = _wasapi_index()
    out = []
    for i, d in enumerate(sd.query_devices()):
        if d["max_output_channels"] <= 0:
            continue
        if api is not None and d["hostapi"] != api:
            continue
        out.append(
            {
                "name": d["name"],
                "index": i,
                "samplerate": int(d["default_samplerate"]),
                "channels": min(2, d["max_output_channels"]),
            }
        )
    return out


def default_output_name():
    api = _wasapi_index()
    if api is None:
        return None
    idx = sd.query_hostapis(api)["default_output_device"]
    if idx is None or idx < 0:
        return None
    return sd.query_devices(idx)["name"]


def resolve(selected, rescan=False):
    """Map stored device names to live device dicts. Missing devices are reported."""
    devices = list_output_devices(rescan)
    by_name = {d["name"]: d for d in devices}
    resolved, missing = [], []
    for name in selected:
        if name == config.DEFAULT_DEVICE:
            name = default_output_name()
            if name is None:
                missing.append("System default")
                continue
        if name in by_name:
            if by_name[name] not in resolved:
                resolved.append(by_name[name])
        else:
            missing.append(name)
    return resolved, missing


# ---------------------------------------------------------------- synthesis


def signal_params(settings):
    preset = config.SIGNAL_PRESETS[settings["signal"]]
    freq = settings["custom_frequency"] if settings["signal"] == "custom" else preset["frequency"]
    return preset["wave"], freq


def synthesize(wave, frequency, level_db, duration, samplerate, channels):
    n = max(1, int(samplerate * duration))
    amp = 10 ** (level_db / 20)
    if wave == "noise":
        rng = np.random.default_rng()
        sig = rng.standard_normal(n)
        sig /= max(1e-9, np.max(np.abs(sig)))
    else:
        # Keep the tone below Nyquist for low-rate devices.
        frequency = min(frequency, samplerate * 0.45)
        t = np.arange(n) / samplerate
        sig = np.sin(2 * np.pi * frequency * t)
    fade = min(int(samplerate * FADE_S), n // 2)
    if fade > 0:
        ramp = 0.5 - 0.5 * np.cos(np.linspace(0, np.pi, fade))
        sig[:fade] *= ramp
        sig[-fade:] *= ramp[::-1]
    sig = (amp * sig).astype(np.float32)
    return np.repeat(sig[:, None], channels, axis=1)


def _play_one(device, wave, frequency, level_db, duration):
    data = synthesize(wave, frequency, level_db, duration, device["samplerate"], device["channels"])
    extra = None
    try:
        extra = sd.WasapiSettings(auto_convert=True)
    except Exception:
        pass
    with sd.OutputStream(
        device=device["index"],
        samplerate=device["samplerate"],
        channels=device["channels"],
        dtype="float32",
        extra_settings=extra,
    ) as stream:
        stream.write(data)


def play(devices, wave, frequency, level_db, duration, on_done):
    """Play the signal on every device concurrently; call on_done(ok_names, errors) from a worker."""

    def run():
        ok, errors = [], {}
        lock = threading.Lock()

        def worker(dev):
            try:
                _play_one(dev, wave, frequency, level_db, duration)
                with lock:
                    ok.append(dev["name"])
            except Exception as e:
                with lock:
                    errors[dev["name"]] = str(e) or e.__class__.__name__

        threads = [threading.Thread(target=worker, args=(d,), daemon=True) for d in devices]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        on_done(ok, errors)

    threading.Thread(target=run, daemon=True).start()


# ---------------------------------------------------------------- metering


class LevelMeter:
    """Reads per-endpoint peak levels via the Windows Core Audio meter API.

    Used to tell whether something else is already playing audio, in which
    case a keepalive pulse is unnecessary. Must be used from one thread.
    """

    def __init__(self):
        self._meters = {}
        self._enum = None
        self.available = False
        try:
            import comtypes
            from pycaw.constants import CLSID_MMDeviceEnumerator
            from pycaw.pycaw import IMMDeviceEnumerator

            try:
                comtypes.CoInitialize()
            except OSError:
                pass
            self._enum = comtypes.CoCreateInstance(
                CLSID_MMDeviceEnumerator, IMMDeviceEnumerator, comtypes.CLSCTX_INPROC_SERVER
            )
            self.available = True
        except Exception:
            self.available = False

    def refresh(self):
        self._meters = {}
        if not self.available:
            return
        try:
            from comtypes import CLSCTX_ALL, GUID
            from pycaw.api.mmdeviceapi.depend import PROPERTYKEY
            from pycaw.constants import DEVICE_STATE, EDataFlow
            from pycaw.pycaw import IAudioMeterInformation

            key = PROPERTYKEY()
            key.fmtid = GUID("{a45c254e-df1c-4efd-8020-67d146a850e0}")
            key.pid = 14  # PKEY_Device_FriendlyName

            col = self._enum.EnumAudioEndpoints(EDataFlow.eRender.value, DEVICE_STATE.ACTIVE.value)
            for i in range(col.GetCount()):
                dev = col.Item(i)
                value = dev.OpenPropertyStore(0).GetValue(key)  # 0 = STGM_READ
                name = value.GetValue()
                value.clear()
                # QueryInterface takes its own reference. Casting the raw pointer
                # instead would make two wrappers that each Release() on GC and crash.
                unknown = dev.Activate(IAudioMeterInformation._iid_, CLSCTX_ALL, None)
                self._meters[name] = unknown.QueryInterface(IAudioMeterInformation)
        except Exception:
            self._meters = {}

    def peak(self, name):
        meter = self._meters.get(name)
        if meter is None:
            return None
        try:
            return float(meter.GetPeakValue())
        except Exception:
            return None
