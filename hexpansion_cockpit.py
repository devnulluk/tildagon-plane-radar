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
        max_rgb,
        pulse_level,
        red_chase_frame,
        scale_rgb,
    )
except ImportError:
    from keebdeck import KeebDeckLights
    from led_radar import (
        colour_sweep_frame,
        cycled_colour_sweep_frame,
        max_rgb,
        pulse_level,
        red_chase_frame,
        scale_rgb,
    )


EEH_LOGO_PIXELS = 14
EEH_LOGO_TYPE = "EEH Logo"
KEYBOARD_BRIGHTNESS_LEVELS = (25, 50, 75, 100)
LOGO_BRIGHTNESS_LEVELS = (5, 10, 25, 50, 75, 100)
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


def startup_frame(count, now_ms=0):
    """A bright green radar flourish used only while Plane Radar starts."""
    count = max(1, int(count))
    return colour_sweep_frame(count, now_ms, (0, 220, 48), step_ms=150)


def highlight_field_frame(count, colours, now_ms=0):
    """Fill an expansion with one calm, unmistakable highlight colour."""
    count = max(1, int(count))
    colours = [tuple(colour) for colour in colours]
    if not colours:
        return [(0, 0, 0) for _ in range(count)]
    colour_ms = 2200
    colour = colours[int(now_ms // colour_ms) % len(colours)]
    level = pulse_level(now_ms, period_ms=2200, minimum=55)
    lit = scale_rgb(colour, level)
    return [lit for _ in range(count)]


def ambient_logo_frame(count, now_ms=0):
    """Two smooth, counter-moving aurora glows with no data semantics."""
    count = max(1, int(count))
    clockwise = (int(now_ms) % 7000) * count / 7000.0
    counter = (-((int(now_ms) % 9000) * count / 9000.0)) % count
    frame = [(0, 3, 2) for _ in range(count)]
    for index in range(count):
        for position, colour, width in (
            (clockwise, (0, 150, 72), 2.8),
            (counter, (0, 62, 170), 2.2),
        ):
            distance = abs(index - position)
            distance = min(distance, count - distance)
            if distance >= width:
                continue
            strength = int((width - distance) * 100 / width)
            glow = tuple(channel * strength // 100 for channel in colour)
            frame[index] = max_rgb(frame[index], glow)
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
            print("plane-radar: EEH Logo lighting on port", port)
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

    def release_to_controller(self):
        """Yield immediately when the official EEH controller is available."""
        if not _eeh_controller_running():
            return False
        self.release(clear=False)
        return True


class HexpansionCockpit:
    """Provide startup, ambient and exceptional-traffic expansion lighting."""

    def __init__(
        self,
        app_instance,
        enabled=True,
        brightness=100,
        logo_brightness=10,
        logo_port="auto",
    ):
        self.keyboard = KeebDeckLights(app_instance)
        self.logo = EEHLogoLights(logo_port)
        self.enabled = bool(enabled)
        self.brightness = self._normalise_keyboard_brightness(brightness)
        self.logo_brightness = self._normalise_logo_brightness(logo_brightness)
        self.last_keyboard_frame = None
        self.last_logo_frame = None

    @staticmethod
    def _normalise_keyboard_brightness(value):
        try:
            value = int(value)
        except (TypeError, ValueError):
            value = 100
        return value if value in KEYBOARD_BRIGHTNESS_LEVELS else 100

    @staticmethod
    def _normalise_logo_brightness(value):
        try:
            value = int(value)
        except (TypeError, ValueError):
            value = 10
        return value if value in LOGO_BRIGHTNESS_LEVELS else 10

    def configure(self, enabled, brightness, logo_brightness, logo_port):
        was_enabled = self.enabled
        old_brightness = self.brightness
        old_logo_brightness = self.logo_brightness
        self.enabled = bool(enabled)
        self.brightness = self._normalise_keyboard_brightness(brightness)
        self.logo_brightness = self._normalise_logo_brightness(logo_brightness)
        old_logo_port = self.logo.port_preference
        self.logo.configure(logo_port)
        if old_brightness != self.brightness:
            self.last_keyboard_frame = None
        if old_logo_brightness != self.logo_brightness:
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

    def _write_keyboard(self, frame_builder):
        keyboard_was_active = bool(getattr(self.keyboard, "active", False))
        keyboard_count = self.keyboard.count()
        if not keyboard_count:
            return
        if not keyboard_was_active:
            self.last_keyboard_frame = None
        frame = scale_frame(frame_builder(keyboard_count), self.brightness)
        if frame != self.last_keyboard_frame and self.keyboard.write(frame):
            self.last_keyboard_frame = frame

    def _write_logo(self, frame_builder):
        logo_was_active = bool(getattr(self.logo, "active", False))
        logo_count = self.logo.count()
        if not logo_count:
            return
        if not logo_was_active:
            self.last_logo_frame = None
        frame = scale_frame(frame_builder(logo_count), self.logo_brightness)
        if frame != self.last_logo_frame and self.logo.write(frame):
            self.last_logo_frame = frame

    def _write_frames(self, keyboard_builder, logo_builder=None):
        if not self.enabled:
            self.release()
            return
        self._write_keyboard(keyboard_builder)
        self._write_logo(logo_builder or keyboard_builder)

    def show_startup(self, now_ms):
        self._write_frames(lambda count: startup_frame(count, now_ms))

    def show_idle(self, now_ms):
        """Restore the keyboard and yield the Logo, or show calm ambience."""
        if not self.enabled:
            self.release()
            return
        self.keyboard.release()
        self.last_keyboard_frame = None
        if self.logo.release_to_controller():
            self.last_logo_frame = None
            return
        self._write_logo(lambda count: ambient_logo_frame(count, now_ms))

    def show_highlight(self, colours, emergency, now_ms):
        colours = [tuple(colour) for colour in colours]
        if emergency:
            colours = [(220, 0, 15)]
        if not colours:
            self.show_idle(now_ms)
            return

        def keyboard_build(count):
            return highlight_field_frame(count, colours, now_ms)

        if emergency:
            def logo_build(count):
                return red_chase_frame(count, now_ms)
        else:
            def logo_build(count):
                return cycled_colour_sweep_frame(
                    count, colours, now_ms, colour_ms=2200, step_ms=150
                )
        self._write_frames(keyboard_build, logo_build)

    def show_demo(self, colour, emergency, now_ms):
        self.show_highlight([colour], emergency, now_ms)
