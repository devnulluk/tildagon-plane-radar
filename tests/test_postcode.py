import unittest

from postcode import normalise_postcode, postcode_coordinates


class PostcodeTests(unittest.TestCase):
    def test_normalise_postcode_accepts_spaces_and_lowercase(self):
        self.assertEqual(normalise_postcode(" cm7 1aa "), "CM71AA")

    def test_postcode_coordinates_extracts_valid_result(self):
        payload = {
            "status": 200,
            "result": {"latitude": 51.878, "longitude": 0.552},
        }
        self.assertEqual(postcode_coordinates(payload), (51.878, 0.552))

    def test_postcode_coordinates_rejects_errors_and_bad_coordinates(self):
        self.assertIsNone(postcode_coordinates({"status": 404, "result": None}))
        self.assertIsNone(
            postcode_coordinates(
                {"status": 200, "result": {"latitude": 91, "longitude": 0}}
            )
        )
