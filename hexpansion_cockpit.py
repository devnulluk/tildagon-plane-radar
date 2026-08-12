"""Capability-safe RGB effects for Plane Radar's known Hexpansions.

Keepdexpansion exposes a shared, leaseable NeoPixel provider.  The EEH Logo
controller instead records an explicit board type for each physical port, so
we honour that assignment (or a deliberate Plane Radar port override) and
never probe an unknown output pin.
"""

import time

try:
    from .keebdeck import KeebDeckLights
    from .led_radar import (
        colour_sweep_frame,
        cycled_colour_sweep_frame,
        pulse_level,
        red_chase_frame,
        scale_rgb,
    )
except ImportError:
    from keebdeck import KeebDeckLights
    from led_radar import (
        colour_sweep_frame,
        cycled_colour_sweep_frame,
        pulse_level,
        red_chase_frame,
        scale_rgb,
    )


EEH_LOGO_PIXELS = 14
EEH_LOGO_TYPE = "EEH Logo"
LOGO_PORT_CHOICES = ("auto", "off", 1, 2, 3, 4, 5, 6)
PORT_PINS = {1: 39, 2: 35, 3: 34, 4: 11, 5: 18, 6: 3}


def normalise_logo_port(value):
    """Return ``auto``, ``off`` or an explicitly valid port number."""
    if value is None:
        return "auto"
    text = str(value).strip().lower()
    if text in ("auto", "off"):
        return text
    try:
        port = int(value)
    except (TypeError, ValueError):
        return "auto"
    return port if port in PORT_PINS else "auto"


def next_logo_port(value):
    current = normalise_logo_port(value)
    try:
        index = LOGO_PORT_CHOICES.index(current)
    except ValueError:
        index = 0
    return LOGO_PORT_CHOICES[(index + 1) % len(LOGO_PORT_CHOICES)]


def logo_port_label(value):
    value = normalise_logo_port(value)
    if isinstance(value, int):
        return "PORT {}".format(value)
    return value.upper()


def configured_logo_port(preference="auto", settings_module=None):
    """Resolve an EEH Logo port without guessing at connected hardware."""
    preference = normalise_logo_port(preference)
    if preference == "off":
        return None
    if isinstance(preference, int):
        return preference
    if settings_module is None:
        try:
            import settings as settings_module
        except ImportError:
            return None
    for port in range(1, 7):
        try:
            board = settings_module.get("drwho.slot.{}".format(port), "None")
        except Exception:
            return None
        if board == EEH_LOGO_TYPE:
            return port
    return None


def traffic_meter_frame(count, colours, now_ms=0):
    """One segment per visible aircraft; animate when the meter overflows."""
    count = max(1, int(count))
    colours = [tuple(colour) for colour in colours]
    if not colours:
        return colour_sweep_frame(count, now_ms, (0, 120, 24), step_ms=150)

    frame = [(0, 2, 1) for _ in range(count)]
    overflow = len(colours) > count
    if overflow:
        start = int(now_ms // 900) % len(colours)
        colours = (colours[start:] + colours[:start])[:count]
        strength = pulse_level(now_ms, period_ms=2200, minimum=65)
    else:
        colours = colours[:count]
        strength = 100

    for index, colour in enumerate(colours):
        scaled = tuple(int(channel) * strength // 100 for channel in colour)
        frame[index] = scaled
    return frame


def follow_progress_frame(count, progress=None, locked=True, now_ms=0):
    """Build route-progress, indeterminate-lock or lost-target lighting."""
    count = max(1, int(count))
    level = pulse_level(now_ms, period_ms=1800, minimum=22)
    if not locked:
        return [(level * 92 // 100, 0, 0) for _ in range(count)]
    if progress is None:
        return [(0, level * 80 // 100, level) for _ in range(count)]

    progress = max(0.0, min(1.0, float(progress)))
    scaled_progress = progress * count
    frame = []
    for index in range(count):
        if index + 1 <= scaled_progress:
            frame.append((0, 105, 58))
        elif index <= scaled_progress < index + 1:
            frame.append((20, 150, 175))
        else:
            frame.append((0, 0, 14))
    if progress >= 1.0:
        frame[-1] = (30, 150, 72)
    return frame


def scale_frame(frame, percent):
    return [scale_rgb(colour, percent) for colour in frame]


def _ticks_ms():
    try:
        return time.ticks_ms()
    except AttributeError:
        return int(time.time() * 1000)


def _ticks_diff(current, previous):
    try:
        return time.ticks_diff(current, previous)
    except AttributeError:
        return current - previous


def _eeh_controller_running():
    """Avoid racing the standalone EEH background effect controller."""
    try:
        from system.scheduler import scheduler

        for running in scheduler.apps:
            cls = running.__class__
            text = (
                getattr(cls, "__name__", "")
                + " "
                + getattr(cls, "__module__", "")
            ).lower()
            if "eehneopixelhexpansions" in text:
                return True
    except Exception:
        pass
    return False


class EEHLogoLights:
    """Direct 14-pixel EEH Logo output, only on an explicitly known port."""

    def __init__(self, port_preference="auto"):
        self.port_preference = normalise_logo_port(port_preference)
        self.port = None
        self.leds = None
        self.active = False
        self.last_attempt_ms = None
        self.conflict_reported = False
        self.unavailable_reported = False

    def configure(self, port_preference):
        preference = normalise_logo_port(port_preference)
        if preference == self.port_preference:
            return
        self.release()
        self.port_preference = preference
        self.last_attempt_ms = None
        self.conflict_reported = False
        self.unavailable_reported = False

    def _retry_ready(self):
        now_ms = _ticks_ms()
        if (
            self.last_attempt_ms is not None
            and _ticks_diff(now_ms, self.last_attempt_ms) < 2000
        ):
            return False
        self.last_attempt_ms = now_ms
        return True

    def acquire(self):
        if self.active:
            return True
        if not self._retry_ready():
            return False
        port = configured_logo_port(self.port_preference)
        if port is None:
            return False
        if _eeh_controller_running():
            if not self.conflict_reported:
                print("plane-radar: EEH controller active; Logo effects paused")
                self.conflict_reported = True
            return False
        try:
            import neopixel
            from machine import Pin

            self.leds = neopixel.NeoPixel(Pin(PORT_PINS[port]), EEH_LOGO_PIXELS)
            self.port = port
            self.active = True
            self.last_attempt_ms = None
            self.conflict_reported = False
            self.unavailable_reported = False
            print("plane-radar: EEH Logo cockpit on port", port)
            return True
        except Exception as exc:
            if not self.unavailable_reported:
                print("plane-radar: EEH Logo unavailable:", exc)
                self.unavailable_reported = True
            self.leds = None
            self.port = None
            self.active = False
            return False

    def count(self):
        return EEH_LOGO_PIXELS if self.acquire() else 0

    def write(self, colours):
        if not self.active and not self.acquire():
            return False
        if _eeh_controller_running():
            self.release(clear=False)
            return False
        try:
            for index in range(EEH_LOGO_PIXELS):
                self.leds[index] = (
                    colours[index] if index < len(colours) else (0, 0, 0)
                )
            self.leds.write()
            return True
        except Exception as exc:
            print("plane-radar: EEH Logo write failed:", exc)
            self.release(clear=False)
            return False

    def release(self, clear=True):
        leds = self.leds
        self.leds = None
        self.port = None
        self.active = False
        self.last_attempt_ms = None
        if leds is None or not clear or _eeh_controller_running():
            return
        try:
            for index in range(EEH_LOGO_PIXELS):
                leds[index] = (0, 0, 0)
            leds.write()
        except Exception:
            pass


class HexpansionCockpit:
    """Synchronise keyboard and EEH Logo with the radar's current state."""

    def __init__(
        self,
        app_instance,
        enabled=True,
        brightness=25,
        logo_port="auto",
    ):
        self.keyboard = KeebDeckLights(app_instance)
        self.logo = EEHLogoLights(logo_port)
        self.enabled = bool(enabled)
        self.brightness = self._normalise_brightness(brightness)
        self.last_keyboard_frame = None
        self.last_logo_frame = None

    @staticmethod
    def _normalise_brightness(value):
        try:
            value = int(value)
        except (TypeError, ValueError):
            value = 25
        return value if value in (25, 50, 75, 100) else 25

    def configure(self, enabled, brightness, logo_port):
        was_enabled = self.enabled
        old_brightness = self.brightness
        self.enabled = bool(enabled)
        self.brightness = self._normalise_brightness(brightness)
        old_logo_port = self.logo.port_preference
        self.logo.configure(logo_port)
        if old_brightness != self.brightness:
            self.last_keyboard_frame = None
            self.last_logo_frame = None
        if old_logo_port != self.logo.port_preference:
            self.last_logo_frame = None
        if was_enabled and not self.enabled:
            self.release()

    def release(self):
        self.keyboard.release()
        self.logo.release()
        self.last_keyboard_frame = None
        self.last_logo_frame = None

    def _write_frames(self, frame_builder):
        if not self.enabled:
            self.release()
            return
        keyboard_was_active = bool(getattr(self.keyboard, "active", False))
        keyboard_count = self.keyboard.count()
        if keyboard_count:
            if not keyboard_was_active:
                self.last_keyboard_frame = None
            frame = scale_frame(frame_builder(keyboard_count), self.brightness)
            if frame != self.last_keyboard_frame and self.keyboard.write(frame):
                self.last_keyboard_frame = frame
        logo_was_active = bool(getattr(self.logo, "active", False))
        logo_count = self.logo.count()
        if logo_count:
            if not logo_was_active:
                self.last_logo_frame = None
            frame = scale_frame(frame_builder(logo_count), self.brightness)
            if frame != self.last_logo_frame and self.logo.write(frame):
                self.last_logo_frame = frame

    def show_local(self, traffic_colours, attention_colours, now_ms):
        if attention_colours:
            def build(count):
                return cycled_colour_sweep_frame(
                    count, attention_colours, now_ms, colour_ms=1800, step_ms=120
                )
        else:
            def build(count):
                return traffic_meter_frame(count, traffic_colours, now_ms)
        self._write_frames(build)

    def show_demo(self, colour, emergency, now_ms):
        if emergency:
            def build(count):
                return red_chase_frame(count, now_ms)
        else:
            def build(count):
                return colour_sweep_frame(count, now_ms, colour, step_ms=120)
        self._write_frames(build)

    def show_follow(self, progress, locked, emergency, now_ms):
        if emergency:
            def build(count):
                return red_chase_frame(count, now_ms)
        else:
            def build(count):
                return follow_progress_frame(count, progress, locked, now_ms)
        self._write_frames(build)
