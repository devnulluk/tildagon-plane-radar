import sys
import types
import unittest

from wifi_location import (
    build_wifi_payload,
    get_wifi_position,
    parse_beacondb_response,
    wait_for_connection,
)


class WiFiLocationTests(unittest.TestCase):
    def test_connection_wait_uses_wlan_state_without_system_wifi(self):
        states = iter((False, False, True))
        station = types.SimpleNamespace(isconnected=lambda: next(states))
        self.assertTrue(wait_for_connection(station, attempts=3, delay_ms=0))

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
            isconnected=lambda: True,
            scan=lambda: [
                (b"ap", bytes((0x20, 1, 2, 3, 4, 7)), 1, -35, 0, False)
            ]
        )
        fake_network = types.SimpleNamespace(
            STA_IF=0,
            WLAN=lambda unused: station,
        )
        original_network = sys.modules.get("network")
        original_wifi = sys.modules.get("wifi")
        sys.modules["network"] = fake_network
        sys.modules["wifi"] = types.SimpleNamespace(
            status=lambda: True,
            connect=lambda: None,
            wait=lambda: True,
        )
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
            if original_wifi is None:
                del sys.modules["wifi"]
            else:
                sys.modules["wifi"] = original_wifi

    def test_espnow_connect_error_still_tries_ip_fallback(self):
        station = types.SimpleNamespace(
            isconnected=lambda: False,
            scan=lambda: (_ for _ in ()).throw(OSError("scan busy")),
        )
        fake_network = types.SimpleNamespace(STA_IF=0, WLAN=lambda unused: station)
        fake_wifi = types.SimpleNamespace(
            status=lambda: False,
            connect=lambda: (_ for _ in ()).throw(OSError("Wifi Internal State Error")),
            wait=lambda: False,
        )

        class Response:
            status_code = 200

            def json(self):
                return {"location": {"lat": 51.8, "lng": 0.5}, "accuracy": 9000}

            def close(self):
                pass

        original_network = sys.modules.get("network")
        original_wifi = sys.modules.get("wifi")
        sys.modules["network"] = fake_network
        sys.modules["wifi"] = fake_wifi
        try:
            requests = types.SimpleNamespace(post=lambda *args, **kwargs: Response())
            self.assertEqual(get_wifi_position(requests), (51.8, 0.5, 9000.0))
        finally:
            if original_network is None:
                del sys.modules["network"]
            else:
                sys.modules["network"] = original_network
            if original_wifi is None:
                del sys.modules["wifi"]
            else:
                sys.modules["wifi"] = original_wifi
