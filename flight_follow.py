"""Helpers for following one live flight and estimating route progress."""
import math

ADSB_CALLSIGN_URL = "https://opendata.adsb.fi/api/v2/callsign/{callsign}"
ADSB_HEX_URL = "https://opendata.adsb.fi/api/v2/hex/{hex_id}"
ROUTE_URL = "https://api.adsbdb.com/v0/callsign/{callsign}"
EARTH_RADIUS_KM = 6371.0088

# Useful passenger-facing IATA prefixes whose ADS-B callsigns normally use a
# different ICAO operator prefix. Unknown prefixes are left untouched.
IATA_TO_ICAO = {
    "BA": "BAW",  # British Airways
    "U2": "EZY",  # easyJet
    "FR": "RYR",  # Ryanair
    "VS": "VIR",  # Virgin Atlantic
    "LS": "EXS",  # Jet2
    "BY": "TOM",  # TUI Airways
    "W9": "WUK",  # Wizz Air UK
}


def is_flight_key(value):
    """MicroPython-safe check for one ASCII callsign character."""
    return (
        isinstance(value, str)
        and len(value) == 1
        and ("A" <= value <= "Z" or "0" <= value <= "9")
    )


def normalise_flight_query(value):
    text = "".join(
        ch for ch in str(value or "").upper() if is_flight_key(ch)
    )
    if len(text) >= 3:
        prefix = text[:2]
        suffix = text[2:]
        if prefix in IATA_TO_ICAO and suffix and "0" <= suffix[0] <= "9":
            text = IATA_TO_ICAO[prefix] + suffix
    return text[:12]


def build_target_url(callsign=None, hex_id=None):
    if hex_id:
        return ADSB_HEX_URL.format(hex_id=str(hex_id).strip().lower())
    callsign = normalise_flight_query(callsign)
    return ADSB_CALLSIGN_URL.format(callsign=callsign)


def build_route_url(callsign, lat, lon):
    return ROUTE_URL.format(callsign=normalise_flight_query(callsign))


def _number(item, *keys):
    for key in keys:
        value = item.get(key)
        if isinstance(value, (int, float)):
            return float(value)
    return None


def _text(item, *keys):
    for key in keys:
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _aircraft_list(payload):
    if not isinstance(payload, dict):
        return []
    for key in ("ac", "aircraft"):
        value = payload.get(key)
        if isinstance(value, list):
            return value
    return []


def parse_target(payload, preferred_hex=None):
    """Return a compact live target dict from an adsb.fi response."""
    preferred = str(preferred_hex or "").lower()
    candidates = []
    for item in _aircraft_list(payload):
        if not isinstance(item, dict):
            continue
        lat, lon = item.get("lat"), item.get("lon")
        if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
            continue
        candidates.append(item)
    if not candidates:
        return None

    raw = candidates[0]
    if preferred:
        for item in candidates:
            if str(item.get("hex", "")).lower() == preferred:
                raw = item
                break

    alt_raw = raw.get("alt_baro")
    if alt_raw == "ground":
        alt_ft = 0.0
        alt = "GND"
    else:
        alt_ft = _number(raw, "alt_baro", "alt_geom")
        if alt_ft is None:
            alt = ""
        elif abs(alt_ft) >= 1000:
            alt = "{}k".format(int(round(alt_ft / 1000.0)))
        else:
            alt = str(int(round(alt_ft)))

    callsign = _text(raw, "flight") or _text(raw, "hex") or "?"
    return {
        "hex": _text(raw, "hex").lower(),
        "callsign": callsign[:12],
        "lat": float(raw["lat"]),
        "lon": float(raw["lon"]),
        "heading": _number(raw, "true_heading", "mag_heading", "track", "dir") or 0.0,
        "track": _number(raw, "track", "true_heading", "mag_heading", "dir") or 0.0,
        "speed": _number(raw, "gs", "tas", "ias") or 0.0,
        "alt": alt,
        "alt_ft": alt_ft,
        "type": _text(raw, "t")[:8],
        "model": _text(raw, "desc")[:36],
        "registration": _text(raw, "r")[:10],
        "squawk": _text(raw, "squawk")[:4],
        "vertical_rate": _number(raw, "baro_rate", "geom_rate"),
        "seen": _number(raw, "seen"),
    }


def great_circle_km(lat1, lon1, lat2, lon2):
    lat1 = math.radians(float(lat1))
    lat2 = math.radians(float(lat2))
    dlat = lat2 - lat1
    dlon = math.radians(float(lon2) - float(lon1))
    a = (
        math.sin(dlat / 2.0) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2.0) ** 2
    )
    return EARTH_RADIUS_KM * 2.0 * math.atan2(
        math.sqrt(a), math.sqrt(max(0.0, 1.0 - a))
    )


def nearest_target_within(payload, center_lat, center_lon, radius_km):
    """Return the nearest positioned target inside a regional radius."""
    if not isinstance(payload, dict):
        return None
    raw_items = payload.get("ac")
    if not isinstance(raw_items, list):
        raw_items = payload.get("aircraft")
    if not isinstance(raw_items, list):
        return None
    nearest = None
    nearest_distance = None
    for raw in raw_items:
        target = parse_target({"ac": [raw]})
        if target is None:
            continue
        distance = great_circle_km(
            center_lat, center_lon, target["lat"], target["lon"]
        )
        if distance > float(radius_km):
            continue
        if nearest_distance is None or distance < nearest_distance:
            nearest = target
            nearest_distance = distance
    return nearest


def _airport_code(airport):
    if not isinstance(airport, dict):
        return "?"
    return _text(airport, "iata", "icao") or "?"


def parse_route(payload):
    """Parse an adsb.lol/VRS route into a small route object."""
    if isinstance(payload, list):
        payload = payload[0] if payload else None
    if not isinstance(payload, dict):
        return None
    response = payload.get("response")
    if isinstance(response, dict):
        route = response.get("flightroute")
        if not isinstance(route, dict):
            return None
        origin = route.get("origin")
        destination = route.get("destination")
        if not isinstance(origin, dict) or not isinstance(destination, dict):
            return None

        def airport_code(airport):
            value = airport.get("iata_code") or airport.get("icao_code")
            return value.strip().upper() if isinstance(value, str) else "?"

        try:
            return {
                "origin": airport_code(origin),
                "destination": airport_code(destination),
                "origin_lat": float(origin["latitude"]),
                "origin_lon": float(origin["longitude"]),
                "destination_lat": float(destination["latitude"]),
                "destination_lon": float(destination["longitude"]),
                "plausible": True,
            }
        except (KeyError, TypeError, ValueError):
            return None
    airports = payload.get("_airports")
    if not isinstance(airports, list) or len(airports) < 2:
        return None
    valid = [
        airport
        for airport in airports
        if isinstance(airport, dict)
        and isinstance(airport.get("lat"), (int, float))
        and isinstance(airport.get("lon"), (int, float))
    ]
    if len(valid) < 2:
        return None
    origin, destination = valid[0], valid[-1]
    return {
        "origin": _airport_code(origin),
        "destination": _airport_code(destination),
        "origin_name": _text(origin, "name", "location"),
        "destination_name": _text(destination, "name", "location"),
        "origin_lat": float(origin["lat"]),
        "origin_lon": float(origin["lon"]),
        "destination_lat": float(destination["lat"]),
        "destination_lon": float(destination["lon"]),
        "codes": _text(payload, "_airport_codes_iata", "airport_codes"),
        "plausible": bool(payload.get("plausible", True)),
        "legs": len(valid) - 1,
    }


def route_progress(route, lat, lon):
    """Estimate route completion from great-circle distance remaining."""
    if not isinstance(route, dict):
        return None
    try:
        total = great_circle_km(
            route["origin_lat"],
            route["origin_lon"],
            route["destination_lat"],
            route["destination_lon"],
        )
        remaining = great_circle_km(
            lat, lon, route["destination_lat"], route["destination_lon"]
        )
    except (KeyError, TypeError, ValueError):
        return None
    if total < 1.0:
        return None
    progress = 1.0 - (remaining / total)
    return max(0.0, min(1.0, progress))


def route_remaining_km(route, lat, lon):
    if not isinstance(route, dict):
        return None
    try:
        return great_circle_km(
            lat, lon, route["destination_lat"], route["destination_lon"]
        )
    except (KeyError, TypeError, ValueError):
        return None


def initial_bearing(lat1, lon1, lat2, lon2):
    """Initial great-circle bearing, north=0/east=90."""
    p1 = math.radians(float(lat1))
    p2 = math.radians(float(lat2))
    dlon = math.radians(float(lon2) - float(lon1))
    y = math.sin(dlon) * math.cos(p2)
    x = (
        math.cos(p1) * math.sin(p2)
        - math.sin(p1) * math.cos(p2) * math.cos(dlon)
    )
    return math.degrees(math.atan2(y, x)) % 360.0
