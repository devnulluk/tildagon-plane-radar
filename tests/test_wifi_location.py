import sys
import types
import unittest

from wifi_location import build_wifi_payload, get_wifi_position, parse_beacondb_response


class WiFiLocationTests(unittest.TestCase):
    def test_scan_payload_filters_local_addresses_and_sorts_by_signal(self):
        rows = [
            (b"weak", bytes((0x10, 1, 2, 3, 4, 5)), 1, -80, 0, False),
            (b"local", bytes((0x12, 1, 2, 3, 4, 6)), 1, -20, 0, False),
            (b"strong", bytes((0x20, 1, 2, 3, 4, 7)), 1, -35, 0, False),
        ]
        points = build_wifi_payload(rows)["wifiAccessPoints"]
        self.assertEqual([point["signalStrength"] for point in points], [-35, -80])
        self.assertEqual(points[0]["macAddress"], "20:01:02:03:04:07")

    def test_response_rejects_bad_or_excessively_broad_estimates(self):
        self.assertEqual(
            parse_beacondb_response(
                {"location": {"lat": 51.8, "lng": 0.5}, "accuracy": 1200}
            ),
            (51.8, 0.5, 1200.0),
        )
        self.assertIsNone(
            parse_beacondb_response(
                {"location": {"lat": 51.8, "lng": 0.5}, "accuracy": 60000}
            )
        )
        self.assertIsNone(parse_beacondb_response({"error": "not found"}))

    def test_service_failure_returns_none_and_preserves_control_flow(self):
        station = types.SimpleNamespace(
            scan=lambda: [
                (b"ap", bytes((0x20, 1, 2, 3, 4, 7)), 1, -35, 0, False)
            ]
        )
        fake_network = types.SimpleNamespace(
            STA_IF=0,
            WLAN=lambda unused: station,
        )
        original_network = sys.modules.get("network")
        original_system = sys.modules.get("system")
        sys.modules["network"] = fake_network
        fake_system = types.ModuleType("system")
        fake_system.wifi = types.SimpleNamespace(wait=lambda: True)
        sys.modules["system"] = fake_system
        try:
            failing_requests = types.SimpleNamespace(
                post=lambda *args, **kwargs: (_ for _ in ()).throw(OSError("down"))
            )
            self.assertIsNone(get_wifi_position(failing_requests))
        finally:
            if original_network is None:
                del sys.modules["network"]
            else:
                sys.modules["network"] = original_network
            if original_system is None:
                del sys.modules["system"]
            else:
                sys.modules["system"] = original_system
