import unittest

from route_lookup import build_route_lookup_url, parse_route_label


class RouteLookupTests(unittest.TestCase):
    def test_url_normalises_callsign_without_cpython_helpers(self):
        self.assertTrue(build_route_lookup_url(" baw 88c ").endswith("/BAW88C"))

    def test_parser_prefers_short_airport_codes(self):
        payload = {"response": {"flightroute": {
            "origin": {"iata_code": "YVR", "icao_code": "CYVR"},
            "destination": {"iata_code": "LHR", "icao_code": "EGLL"},
        }}}
        self.assertEqual(parse_route_label(payload), "YVR-LHR")

    def test_parser_rejects_missing_route(self):
        self.assertIsNone(parse_route_label({"response": {}}))


if __name__ == "__main__":
    unittest.main()
