import unittest

from led_radar import bearing_from_offsets, led_index_for_bearing, led_index_from_offsets
from location_provider import normalise_position


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


if __name__ == "__main__":
    unittest.main()
