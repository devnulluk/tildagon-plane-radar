import unittest

from flight_follow import (
    build_target_url,
    great_circle_km,
    initial_bearing,
    is_flight_key,
    nearest_target_within,
    normalise_flight_query,
    parse_route,
    parse_target,
    route_progress,
)


class FlightQueryTests(unittest.TestCase):
    def test_common_iata_prefix_is_converted(self):
        self.assertEqual(normalise_flight_query("BA 123"), "BAW123")
        self.assertEqual(normalise_flight_query("U2123"), "EZY123")

    def test_existing_icao_callsign_is_unchanged(self):
        self.assertEqual(normalise_flight_query("BAW123"), "BAW123")
        self.assertEqual(normalise_flight_query("RYR82TK"), "RYR82TK")

    def test_target_url_can_use_stable_hex(self):
        self.assertTrue(build_target_url(hex_id="406ABC").endswith("/406abc"))

    def test_keyboard_character_check_does_not_need_cpython_string_helpers(self):
        self.assertTrue(is_flight_key("A"))
        self.assertTrue(is_flight_key("7"))
        self.assertFalse(is_flight_key("-"))
        self.assertFalse(is_flight_key("ENTER"))


class TargetParsingTests(unittest.TestCase):
    def test_live_target_fields(self):
        target = parse_target({"ac": [{
            "hex": "406abc",
            "flight": "BAW123 ",
            "lat": 51.0,
            "lon": 0.1,
            "alt_baro": 32000,
            "gs": 451.2,
            "track": 92.0,
            "t": "A320",
            "desc": "Airbus A320-214",
            "r": "G-TEST",
            "squawk": "1234",
        }]})
        self.assertEqual(target["callsign"], "BAW123")
        self.assertEqual(target["hex"], "406abc")
        self.assertEqual(target["alt_ft"], 32000.0)
        self.assertEqual(target["registration"], "G-TEST")
        self.assertEqual(target["model"], "Airbus A320-214")

    def test_target_without_position_is_not_followable(self):
        self.assertIsNone(parse_target({"ac": [{"flight": "BAW123"}]}))

    def test_regional_emergency_filter_chooses_nearest_in_range(self):
        payload = {"ac": [
            {"flight": "FAR", "lat": 60.0, "lon": 10.0},
            {"flight": "NEAR", "lat": 52.0, "lon": 0.1},
        ]}
        target = nearest_target_within(payload, 51.8, 0.0, 500)
        self.assertEqual(target["callsign"], "NEAR")
        self.assertIsNone(nearest_target_within(payload, 0.0, 0.0, 100))


class RouteProgressTests(unittest.TestCase):
    def setUp(self):
        self.route = parse_route({
            "_airport_codes_iata": "LHR-JFK",
            "_airports": [
                {"iata": "LHR", "lat": 51.4700, "lon": -0.4543},
                {"iata": "JFK", "lat": 40.6413, "lon": -73.7781},
            ],
            "plausible": 1,
        })

    def test_route_endpoints(self):
        self.assertEqual(self.route["origin"], "LHR")
        self.assertEqual(self.route["destination"], "JFK")

    def test_adsbdb_route_shape(self):
        route = parse_route({"response": {"flightroute": {
            "origin": {"iata_code": "YVR", "latitude": 49.19, "longitude": -123.18},
            "destination": {"iata_code": "LHR", "latitude": 51.47, "longitude": -0.46},
        }}})
        self.assertEqual(route["origin"], "YVR")
        self.assertEqual(route["destination"], "LHR")

    def test_progress_is_zero_at_origin_and_one_at_destination(self):
        self.assertAlmostEqual(route_progress(self.route, 51.4700, -0.4543), 0.0)
        self.assertAlmostEqual(route_progress(self.route, 40.6413, -73.7781), 1.0)

    def test_distance_and_bearing_are_sensible(self):
        distance = great_circle_km(51.4700, -0.4543, 40.6413, -73.7781)
        self.assertGreater(distance, 5400)
        self.assertLess(distance, 5700)
        bearing = initial_bearing(51.4700, -0.4543, 40.6413, -73.7781)
        self.assertGreater(bearing, 270)
        self.assertLess(bearing, 310)


if __name__ == "__main__":
    unittest.main()
