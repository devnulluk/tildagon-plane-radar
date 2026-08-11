import unittest
from adsb import (
    build_squawk_url,
    build_url,
    classify_aircraft,
    classify_attention,
    needs_emergency_focus,
    parse_aircraft,
)

class AdsbTests(unittest.TestCase):
    def test_url_uses_nautical_miles(self):
        url=build_url(51.5,-0.1,18.52); self.assertIn("lat/51.500000/lon/-0.100000",url); self.assertTrue(url.endswith("/dist/10.0"))
    def test_squawk_url_validates_octal_code(self):
        self.assertTrue(build_squawk_url("7700").endswith("/sqk/7700"))
        with self.assertRaises(ValueError): build_squawk_url("8900")
    def test_parser_normalises_preferred_fields(self):
        payload={"ac":[{"lat":51.51,"lon":-0.12,"flight":" BAW123 ","hex":"400abc","t":"A320","true_heading":92.0,"track":95.0,"gs":410.0,"alt_baro":35025,"squawk":"7700","emergency":"general"}]}
        item=parse_aircraft(payload)[0]; self.assertEqual(item["callsign"],"BAW123"); self.assertEqual(item["icao"],"400abc"); self.assertEqual(item["type"],"A320"); self.assertEqual(item["heading"],92.0); self.assertEqual(item["track"],95.0); self.assertEqual(item["speed"],410.0); self.assertEqual(item["alt"],"35k"); self.assertEqual(item["squawk"],"7700"); self.assertEqual(item["emergency"],"general")
    def test_parser_falls_back_to_hex_and_track(self):
        item=parse_aircraft({"ac":[{"lat":51.0,"lon":0.0,"hex":"abc123","track":270,"ias":120,"alt_geom":950}]})[0]
        self.assertEqual(item["callsign"],"abc123"); self.assertEqual(item["heading"],270.0); self.assertEqual(item["speed"],120.0); self.assertEqual(item["alt"],"950")
    def test_ground_aircraft_are_hidden_by_default(self):
        payload={"ac":[{"lat":51.0,"lon":0.0,"alt_baro":"ground"}]}; self.assertEqual(parse_aircraft(payload),[]); self.assertEqual(len(parse_aircraft(payload,show_ground=True)),1)
    def test_missing_coordinates_are_skipped(self):
        self.assertEqual(len(parse_aircraft({"ac":[{"flight":"NOLOC"},{"lat":51.0,"lon":0.0}]})),1)

    def test_aircraft_classification_prefers_military_flag(self):
        self.assertEqual(
            classify_aircraft({"dbFlags": 1, "category": "A7"}),
            "military",
        )

    def test_aircraft_categories_select_safe_display_symbols(self):
        self.assertEqual(classify_aircraft({"category": "A7"}), "helicopter")
        self.assertEqual(classify_aircraft({"category": "A1"}), "ga")
        self.assertEqual(classify_aircraft({"category": "B4"}), "ga")
        self.assertEqual(classify_aircraft({"category": "A3"}), "civilian")
        self.assertEqual(classify_aircraft({}), "civilian")

    def test_parser_preserves_symbol_metadata(self):
        item = parse_aircraft({
            "ac": [{
                "lat": 51.0,
                "lon": 0.0,
                "category": "A7",
                "dbFlags": 0,
            }]
        })[0]
        self.assertEqual(item["category"], "A7")
        self.assertEqual(item["db_flags"], 0)
        self.assertEqual(item["kind"], "helicopter")

    def test_attention_classification_uses_narrow_verified_signals(self):
        self.assertEqual(classify_attention({"flight": "HLE72"}), "air_ambulance")
        self.assertEqual(
            classify_attention({"emergency": "lifeguard"}),
            "air_ambulance",
        )
        self.assertEqual(classify_attention({"flight": "UKP151"}), "police")
        self.assertEqual(classify_attention({"r": "G-POLB"}), "police")
        self.assertEqual(classify_attention({"dbFlags": 1}), "military")
        self.assertEqual(classify_attention({"dbFlags": 2}), "interesting")
        self.assertEqual(classify_attention({"flight": "BAW123"}), "")

    def test_parser_preserves_compact_interesting_marker(self):
        item = parse_aircraft({
            "ac": [{
                "lat": 51.0,
                "lon": 0.0,
                "flight": "HLE72",
            }]
        })[0]
        self.assertEqual(item["attention"], "air_ambulance")

        ordinary = parse_aircraft({
            "ac": [{"lat": 51.0, "lon": 0.0, "flight": "BAW123"}]
        })[0]
        self.assertNotIn("attention", ordinary)

    def test_lifeguard_is_green_attention_not_red_emergency_focus(self):
        item = {"emergency": "lifeguard"}
        self.assertEqual(classify_attention(item), "air_ambulance")
        self.assertFalse(needs_emergency_focus(item))
        self.assertTrue(needs_emergency_focus({"squawk": "7700"}))
        self.assertTrue(needs_emergency_focus({"emergency": "general"}))
