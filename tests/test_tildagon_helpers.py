import unittest

from led_radar import (
    bearing_from_offsets,
    colour_sweep_frame,
    cycled_colour_sweep_frame,
    led_index_for_bearing,
    led_index_from_offsets,
    pulse_level,
    red_chase_frame,
)
from location_provider import normalise_position
from spaceagon import (
    angular_distance,
    calibrated_heading,
    parse_manual_bearing,
    raw_compass_heading,
    relative_bearing,
    rotate_screen_xy,
    touch_bearing,
    zoom_index,
)


class LocationProviderTests(unittest.TestCase):
    def test_valid_position(self):
        self.assertEqual(normalise_position((51.5, -0.12)), (51.5, -0.12))

    def test_invalid_position(self):
        self.assertIsNone(normalise_position((91, 0)))
        self.assertIsNone(normalise_position((0, -181)))
        self.assertIsNone(normalise_position(None))


class LEDRadarTests(unittest.TestCase):
    def test_cardinal_bearings(self):
        self.assertAlmostEqual(bearing_from_offsets(0, 1), 0.0)
        self.assertAlmostEqual(bearing_from_offsets(1, 0), 90.0)
        self.assertAlmostEqual(bearing_from_offsets(0, -1), 180.0)
        self.assertAlmostEqual(bearing_from_offsets(-1, 0), 270.0)

    def test_led_ring_wraps_at_north(self):
        self.assertEqual(led_index_for_bearing(0), 1)
        self.assertEqual(led_index_for_bearing(350), 12)
        self.assertEqual(led_index_for_bearing(360), 1)

    def test_offset_maps_to_led(self):
        self.assertEqual(led_index_from_offsets(0, 1), 1)
        self.assertEqual(led_index_from_offsets(0, -1), 7)
        self.assertIsNone(led_index_from_offsets(0, 0))

    def test_attention_pulse_is_smooth_and_never_dark(self):
        self.assertEqual(pulse_level(0), 28)
        self.assertEqual(pulse_level(1200), 100)
        self.assertEqual(pulse_level(2400), 28)
        samples = [pulse_level(value) for value in range(0, 2400, 100)]
        self.assertGreaterEqual(min(samples), 28)
        self.assertLessEqual(max(samples), 100)

    def test_emergency_chase_moves_without_flashing_the_ring(self):
        first = red_chase_frame(12, 0)
        second = red_chase_frame(12, 90)
        self.assertEqual(len(first), 12)
        self.assertNotEqual(first, second)
        self.assertEqual(first[0], (180, 0, 0))
        self.assertEqual(first[6], (180, 0, 0))
        self.assertEqual(second[1], (180, 0, 0))
        self.assertEqual(second[7], (180, 0, 0))
        self.assertTrue(all(colour[0] > 0 for colour in first))

    def test_multi_alert_sweep_cycles_each_colour(self):
        colours = ((0, 180, 45), (0, 55, 220), (220, 0, 15))
        green = cycled_colour_sweep_frame(12, colours, 0)
        blue = cycled_colour_sweep_frame(12, colours, 1800)
        red = cycled_colour_sweep_frame(12, colours, 3600)
        self.assertEqual(green[0], (0, 180, 45))
        self.assertEqual(blue[0], (0, 55, 220))
        self.assertEqual(red[0], (220, 0, 15))
        moved = colour_sweep_frame(12, 120, colours[0])
        self.assertEqual(moved[1], (0, 180, 45))
        self.assertNotEqual(moved, green)


class SpaceagonTests(unittest.TestCase):
    def test_clock_touch_bearings(self):
        self.assertEqual(touch_bearing("TOUCH12"), 0.0)
        self.assertEqual(touch_bearing("TOUCH03"), 90.0)
        self.assertEqual(touch_bearing("TOUCH06"), 180.0)
        self.assertEqual(touch_bearing("TOUCH09"), 270.0)
        self.assertIsNone(touch_bearing("TOUCH13"))

    def test_relative_bearing_and_wrap(self):
        self.assertEqual(relative_bearing(90, 30), 60.0)
        self.assertEqual(relative_bearing(10, 350), 20.0)
        self.assertEqual(angular_distance(350, 10), 20.0)

    def test_heading_up_rotation(self):
        x, y = rotate_screen_xy(10, 0, 90)
        self.assertAlmostEqual(x, 0.0, places=6)
        self.assertAlmostEqual(y, -10.0, places=6)

    def test_compass_zero_calibration(self):
        raw = raw_compass_heading((1, 1, 0))
        self.assertAlmostEqual(raw, 45.0)
        self.assertAlmostEqual(calibrated_heading(raw, 45), 0.0)

    def test_proximity_zoom_clamps(self):
        self.assertEqual(zoom_index(1, -1, 4), 0)
        self.assertEqual(zoom_index(1, 1, 4), 2)
        self.assertEqual(zoom_index(0, -1, 4), 0)
        self.assertEqual(zoom_index(3, 1, 4), 3)

    def test_manual_bearing_accepts_degrees_and_north_reset(self):
        self.assertEqual(parse_manual_bearing("320"), 320.0)
        self.assertEqual(parse_manual_bearing(0), 0.0)
        self.assertIsNone(parse_manual_bearing("north"))
        with self.assertRaises(ValueError):
            parse_manual_bearing("360")
        with self.assertRaises(ValueError):
            parse_manual_bearing("west")


if __name__ == "__main__":
    unittest.main()
