import unittest

from led_radar import bearing_from_offsets, led_index_for_bearing, led_index_from_offsets
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
