import unittest
import sys
import types
from unittest.mock import patch

from hexpansion_cockpit import (
    HexpansionCockpit,
    EEHLogoLights,
    ambient_logo_frame,
    configured_logo_port,
    highlight_field_frame,
    logo_port_label,
    next_logo_port,
    normalise_logo_port,
    startup_frame,
)
from keebdeck import KeebDeckLights


class FakeSettings:
    def __init__(self, values=None):
        self.values = values or {}

    def get(self, key, default=None):
        return self.values.get(key, default)


class FakePixels:
    def __init__(self, colours):
        self.colours = list(colours)
        self.n = len(self.colours)
        self.writes = 0

    def __getitem__(self, index):
        return self.colours[index]

    def __setitem__(self, index, colour):
        self.colours[index] = colour

    def write(self):
        self.writes += 1


class KeyboardProvider:
    def __init__(self):
        self.leds = FakePixels([(3, 4, 5)] * 5)
        self.led_owner = None
        self.follow_pattern = False


class FakeOutput:
    def __init__(self, count):
        self.pixel_count = count
        self.frames = []
        self.releases = 0
        self.active = True
        self.port_preference = "auto"
        self.controller_available = False

    def count(self):
        return self.pixel_count

    def write(self, frame):
        self.frames.append(frame)
        return True

    def release(self):
        self.releases += 1
        self.active = False

    def configure(self, value):
        self.port_preference = value

    def release_to_controller(self):
        if not self.controller_available:
            return False
        self.release()
        return True


class HexpansionHelperTests(unittest.TestCase):
    def test_logo_port_is_never_guessed(self):
        empty = FakeSettings()
        configured = FakeSettings({"drwho.slot.4": "EEH Logo"})
        self.assertIsNone(configured_logo_port("auto", empty))
        self.assertEqual(configured_logo_port("auto", configured), 4)
        self.assertEqual(configured_logo_port(6, empty), 6)
        self.assertIsNone(configured_logo_port("off", configured))

    def test_logo_port_menu_cycles_and_normalises(self):
        self.assertEqual(normalise_logo_port("nonsense"), "auto")
        self.assertEqual(next_logo_port("auto"), "off")
        self.assertEqual(next_logo_port("off"), 1)
        self.assertEqual(next_logo_port(6), "auto")
        self.assertEqual(logo_port_label(3), "PORT 3")

    def test_startup_has_a_moving_green_scanner(self):
        first = startup_frame(5, 0)
        second = startup_frame(5, 150)
        self.assertNotEqual(first, second)
        self.assertEqual(first[0], (0, 220, 48))
        self.assertEqual(second[1], (0, 220, 48))

    def test_highlight_is_a_calm_full_colour_field(self):
        frame = highlight_field_frame(5, [(0, 180, 45)], 1100)
        self.assertEqual(frame, [(0, 180, 45)] * 5)

    def test_idle_logo_aurora_moves_without_encoding_traffic(self):
        first = ambient_logo_frame(14, 0)
        second = ambient_logo_frame(14, 500)
        self.assertEqual(len(first), 14)
        self.assertNotEqual(first, second)

    def test_cockpit_scales_each_device_to_selected_brightness(self):
        cockpit = HexpansionCockpit(
            object(), brightness=25, logo_brightness=10
        )
        cockpit.keyboard = FakeOutput(5)
        cockpit.logo = FakeOutput(14)
        cockpit.show_startup(0)
        self.assertEqual(cockpit.keyboard.frames[-1][0], (0, 55, 12))
        self.assertEqual(cockpit.logo.frames[-1][0], (0, 22, 4))
        self.assertEqual(len(cockpit.keyboard.frames[-1]), 5)
        self.assertEqual(len(cockpit.logo.frames[-1]), 14)

    def test_cockpit_defaults_keyboard_to_full_and_logo_to_ten_percent(self):
        cockpit = HexpansionCockpit(object())
        cockpit.keyboard = FakeOutput(5)
        cockpit.logo = FakeOutput(14)
        cockpit.show_startup(0)
        self.assertEqual(cockpit.keyboard.frames[-1][0], (0, 220, 48))
        self.assertEqual(cockpit.logo.frames[-1][0], (0, 22, 4))

    def test_identical_static_frames_are_not_rewritten(self):
        cockpit = HexpansionCockpit(object(), brightness=25)
        cockpit.keyboard = FakeOutput(5)
        cockpit.logo = FakeOutput(14)
        cockpit.show_highlight([(200, 100, 40)], False, 1100)
        cockpit.show_highlight([(200, 100, 40)], False, 1100)
        self.assertEqual(len(cockpit.keyboard.frames), 1)
        self.assertEqual(len(cockpit.logo.frames), 1)

    def test_logo_brightness_changes_independently_from_keyboard(self):
        cockpit = HexpansionCockpit(
            object(), brightness=25, logo_brightness=10
        )
        cockpit.keyboard = FakeOutput(5)
        cockpit.logo = FakeOutput(14)
        cockpit.show_startup(0)
        cockpit.configure(True, 25, 5, "auto")
        cockpit.show_startup(0)
        self.assertEqual(len(cockpit.keyboard.frames), 1)
        self.assertEqual(cockpit.keyboard.frames[-1][0], (0, 55, 12))
        self.assertEqual(len(cockpit.logo.frames), 2)
        self.assertEqual(cockpit.logo.frames[-1][0], (0, 11, 2))

    def test_idle_restores_keyboard_and_hands_logo_to_controller(self):
        cockpit = HexpansionCockpit(object())
        cockpit.keyboard = FakeOutput(5)
        cockpit.logo = FakeOutput(14)
        cockpit.logo.controller_available = True
        cockpit.show_startup(0)
        cockpit.show_idle(100)
        self.assertEqual(cockpit.keyboard.releases, 1)
        self.assertEqual(cockpit.logo.releases, 1)

    def test_idle_uses_logo_aurora_only_when_no_controller_can_take_it(self):
        cockpit = HexpansionCockpit(object())
        cockpit.keyboard = FakeOutput(5)
        cockpit.logo = FakeOutput(14)
        cockpit.show_startup(0)
        cockpit.show_idle(500)
        self.assertEqual(cockpit.keyboard.releases, 1)
        self.assertEqual(cockpit.logo.releases, 0)
        self.assertEqual(len(cockpit.logo.frames), 2)


class EEHLogoDriverTests(unittest.TestCase):
    def test_explicit_port_uses_official_pin_map_and_clears_on_release(self):
        pixels = FakePixels([(0, 0, 0)] * 14)
        captured = {}

        def make_pixels(pin, count):
            captured["pin"] = pin
            captured["count"] = count
            return pixels

        machine = types.SimpleNamespace(Pin=lambda pin: pin)
        neopixel = types.SimpleNamespace(NeoPixel=make_pixels)
        lights = EEHLogoLights(4)
        with patch.dict(sys.modules, {"machine": machine, "neopixel": neopixel}):
            with patch("hexpansion_cockpit._eeh_controller_running", return_value=False):
                self.assertTrue(lights.acquire())
                self.assertEqual(captured, {"pin": 11, "count": 14})
                self.assertTrue(lights.write([(12, 34, 56)] * 14))
                self.assertEqual(pixels.colours, [(12, 34, 56)] * 14)
                lights.release()
        self.assertEqual(pixels.colours, [(0, 0, 0)] * 14)

    def test_active_eeh_controller_prevents_direct_acquisition(self):
        lights = EEHLogoLights(6)
        with patch("hexpansion_cockpit._eeh_controller_running", return_value=True):
            self.assertFalse(lights.acquire())
        self.assertFalse(lights.active)

    def test_release_to_controller_does_not_clear_its_next_frame(self):
        pixels = FakePixels([(12, 34, 56)] * 14)
        lights = EEHLogoLights(6)
        lights.leds = pixels
        lights.port = 6
        lights.active = True
        with patch("hexpansion_cockpit._eeh_controller_running", return_value=True):
            self.assertTrue(lights.release_to_controller())
        self.assertFalse(lights.active)
        self.assertEqual(pixels.colours, [(12, 34, 56)] * 14)


class KeepdexpansionLeaseTests(unittest.TestCase):
    def test_static_keyboard_colours_are_restored_after_release(self):
        provider = KeyboardProvider()
        app_instance = object()
        lights = KeebDeckLights(app_instance)
        with patch("keebdeck.find_keebdeck", return_value=provider):
            self.assertTrue(lights.acquire())
            self.assertTrue(lights.write([(20, 0, 0)] * 5))
            self.assertEqual(provider.led_owner, app_instance)
            lights.release()
        self.assertEqual(provider.led_owner, None)
        self.assertEqual(provider.leds.colours, [(3, 4, 5)] * 5)


if __name__ == "__main__":
    unittest.main()
