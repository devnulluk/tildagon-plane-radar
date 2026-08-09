"""Optional Keepdexpansion discovery and RGB-backlight helpers."""

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
    def __init__(self, app_instance):
        self.app_instance = app_instance
        self.provider = None
        self.active = False

    def acquire(self):
        if self.active:
            return True
        provider = find_keebdeck()
        if provider is None:
            return False
        try:
            current = getattr(provider, "led_owner", None)
            if current is not None and current is not self.app_instance:
                return False
            provider.led_owner = self.app_instance
            self.provider = provider
            self.active = True
            return True
        except Exception:
            self.provider = None
            self.active = False
            return False

    def release(self):
        provider = self.provider
        self.provider = None
        self.active = False
        if provider is None:
            return
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
                leds[index] = colours[index] if index < len(colours) else (0, 0, 0)
            leds.write()
            return True
        except Exception:
            self.release()
            return False

    def paint(self, progress=None, locked=True, pulse=False):
        if not self.active and not self.acquire():
            return False
        try:
            count = int(getattr(self.provider.leds, "n", 0))
        except Exception:
            count = 0
        if count <= 0:
            return False
        if not locked:
            level = 70 if pulse else 18
            return self._write([(level, 0, 0)] * count)
        if progress is None:
            level = 80 if pulse else 32
            return self._write([(0, level, level)] * count)
        progress = max(0.0, min(1.0, float(progress)))
        scaled = progress * count
        colours = []
        for index in range(count):
            if index + 1 <= scaled:
                colours.append((0, 72, 44))
            elif index <= scaled < index + 1:
                colours.append((15, 105 if pulse else 70, 115 if pulse else 80))
            else:
                colours.append((0, 0, 8))
        if progress >= 1.0:
            colours[-1] = (30, 110, 55) if pulse else (0, 78, 40)
        return self._write(colours)
