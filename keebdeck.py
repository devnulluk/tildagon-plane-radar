"""Optional Keepdexpansion discovery and RGB-backlight helpers."""

import time

MERGED_NEOPIXELS = (
    "https://tildagon.badge.emfcamp.org/capabilities/registry/merged_neopixels/"
)
NEOPIXELS = "https://tildagon.badge.emfcamp.org/capabilities/registry/neopixels/"


def _looks_like_keyboard(provider):
    name = provider.__class__.__name__.lower()
    module = getattr(provider.__class__, "__module__", "").lower()
    text = name + " " + module
    return "keyboard" in text or "keeb" in text


def find_keebdeck():
    """Return a running Keepdexpansion-style RGB keyboard provider, or None."""
    try:
        from system.capabilities.utils import get_running_apps_by_capability

        for capability in (MERGED_NEOPIXELS, NEOPIXELS):
            for provider in get_running_apps_by_capability(capability):
                if _looks_like_keyboard(provider) and hasattr(provider, "leds"):
                    return provider
    except Exception:
        pass
    return None


class KeebDeckLights:
    """Use keyboard backlights temporarily and restore their previous state."""

    def __init__(self, app_instance):
        self.app_instance = app_instance
        self.provider = None
        self.active = False
        self.saved_colours = None
        self.saved_follow_pattern = None
        self.last_attempt_ms = None

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
        provider = find_keebdeck()
        if provider is None:
            return False
        try:
            current = getattr(provider, "led_owner", None)
            if current is not None and current is not self.app_instance:
                return False
            leds = provider.leds
            count = int(getattr(leds, "n", 0))
            try:
                self.saved_colours = [leds[index] for index in range(count)]
            except Exception:
                self.saved_colours = None
            self.saved_follow_pattern = getattr(provider, "follow_pattern", None)
            provider.led_owner = self.app_instance
            self.provider = provider
            self.active = True
            self.last_attempt_ms = None
            return True
        except Exception:
            self.provider = None
            self.active = False
            return False

    def release(self):
        provider = self.provider
        saved_colours = self.saved_colours
        saved_follow_pattern = self.saved_follow_pattern
        self.provider = None
        self.active = False
        self.saved_colours = None
        self.saved_follow_pattern = None
        if provider is None:
            return
        try:
            if saved_follow_pattern is False and saved_colours:
                leds = provider.leds
                count = min(int(getattr(leds, "n", 0)), len(saved_colours))
                for index in range(count):
                    leds[index] = saved_colours[index]
                leds.write()
            if getattr(provider, "led_owner", None) is self.app_instance:
                provider.led_owner = None
        except Exception:
            try:
                if getattr(provider, "led_owner", None) is self.app_instance:
                    provider.led_owner = None
            except Exception:
                pass

    def _write(self, colours):
        if not self.active and not self.acquire():
            return False
        try:
            leds = self.provider.leds
            count = int(getattr(leds, "n", len(colours)))
            if count <= 0:
                return False
            for index in range(count):
                leds[index] = (
                    colours[index] if index < len(colours) else (0, 0, 0)
                )
            leds.write()
            return True
        except Exception:
            self.release()
            return False

    def count(self):
        """Return the driver's logical RGB-zone count, acquiring if needed."""
        if not self.active and not self.acquire():
            return 0
        try:
            return max(0, int(getattr(self.provider.leds, "n", 0)))
        except Exception:
            self.release()
            return 0

    def write(self, colours):
        """Public frame writer used by the Hexpansion cockpit."""
        return self._write(colours)

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
