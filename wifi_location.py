"""Best-effort Wi-Fi positioning through the public BeaconDB endpoint."""
import json
import time

BEACONDB_URL = "https://api.beacondb.net/v1/geolocate"
MAX_ACCESS_POINTS = 12
MAX_ACCURACY_METRES = 50000.0


def _mac_text(bssid):
    if not isinstance(bssid, (bytes, bytearray)) or len(bssid) != 6:
        return None
    if bssid[0] & 3:  # Ignore locally administered and multicast addresses.
        return None
    return ":".join("{:02x}".format(value) for value in bssid)


def build_wifi_payload(scan_results):
    """Build a compact Ichnaea request from MicroPython WLAN.scan() rows."""
    access_points = []
    for row in scan_results or ():
        try:
            mac = _mac_text(row[1])
            signal = int(row[3])
        except Exception:
            continue
        if mac is not None and -128 <= signal <= -10:
            access_points.append({"macAddress": mac, "signalStrength": signal})
    access_points.sort(key=lambda item: item["signalStrength"], reverse=True)
    return {
        "considerIp": True,
        "wifiAccessPoints": access_points[:MAX_ACCESS_POINTS],
    }


def parse_beacondb_response(payload, max_accuracy=MAX_ACCURACY_METRES):
    """Return (lat, lon, accuracy_m), rejecting unusably broad estimates."""
    if not isinstance(payload, dict):
        return None
    location = payload.get("location")
    if not isinstance(location, dict):
        return None
    try:
        lat = float(location.get("lat"))
        lon = float(location.get("lng"))
        accuracy = float(payload.get("accuracy"))
    except (TypeError, ValueError):
        return None
    if not -90 <= lat <= 90 or not -180 <= lon <= 180:
        return None
    if accuracy < 0 or accuracy > max_accuracy:
        return None
    return lat, lon, accuracy


def wait_for_connection(station, attempts=24, delay_ms=250):
    """Wait briefly for the existing station connection without OS helpers."""
    for unused in range(attempts):
        try:
            if station.isconnected():
                return True
        except Exception:
            return False
        if delay_ms:
            sleeper = getattr(time, "sleep_ms", None)
            if sleeper is not None:
                sleeper(delay_ms)
            else:
                time.sleep(delay_ms / 1000.0)
    return False


def get_wifi_position(requests_module, timeout=6):
    """Scan once and query BeaconDB; return None on every failure mode."""
    response = None
    try:
        import network
        try:
            import wifi

            if not wifi.status():
                print("plane-radar: connecting Wi-Fi for location")
                wifi.connect()
                if not wifi.wait():
                    print("plane-radar: Wi-Fi connection unavailable")
                    return None
        except ImportError:
            wifi = None

        station_id = getattr(network, "STA_IF", None)
        if station_id is None:
            station_id = network.WLAN.IF_STA
        station = network.WLAN(station_id)
        if wifi is None and not wait_for_connection(station):
            print("plane-radar: WLAN station did not connect")
            return None
        try:
            scan_results = station.scan()
        except Exception as exc:
            # ESP-NOW firmware can temporarily reject active scans. BeaconDB
            # can still provide its coarser IP-based estimate.
            print("plane-radar: Wi-Fi scan unavailable:", exc)
            scan_results = ()
        payload = build_wifi_payload(scan_results)
        if not payload["wifiAccessPoints"]:
            print("plane-radar: using BeaconDB IP fallback")
        response = requests_module.post(
            BEACONDB_URL,
            data=json.dumps(payload),
            headers={
                "Content-Type": "application/json",
                "User-Agent": "Tildagon-Plane-Radar/0.1",
            },
            timeout=timeout,
        )
        if getattr(response, "status_code", 200) != 200:
            print(
                "plane-radar: BeaconDB HTTP",
                getattr(response, "status_code", "?"),
            )
            return None
        result = parse_beacondb_response(response.json())
        if result is None:
            print("plane-radar: BeaconDB returned no usable estimate")
        return result
    except Exception as exc:
        print("plane-radar: Wi-Fi location failed:", exc)
        return None
    finally:
        if response is not None:
            try:
                response.close()
            except Exception:
                pass
