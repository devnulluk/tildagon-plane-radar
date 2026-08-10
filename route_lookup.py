"""Small, session-only flight-route lookup helpers."""

ROUTE_URL = "https://api.adsbdb.com/v0/callsign/{callsign}"


def build_route_lookup_url(callsign):
    value = "".join(
        char
        for char in str(callsign or "").upper()
        if "A" <= char <= "Z" or "0" <= char <= "9"
    )
    return ROUTE_URL.format(callsign=value[:12])


def parse_route_label(payload):
    """Return an IATA-style ORG-DST label, or None when unavailable."""
    if not isinstance(payload, dict):
        return None
    response = payload.get("response")
    if not isinstance(response, dict):
        return None
    route = response.get("flightroute")
    if not isinstance(route, dict):
        return None
    origin = route.get("origin")
    destination = route.get("destination")
    if not isinstance(origin, dict) or not isinstance(destination, dict):
        return None

    def code(airport):
        value = airport.get("iata_code") or airport.get("icao_code")
        if not isinstance(value, str):
            return ""
        return value.strip().upper()[:4]

    origin_code = code(origin)
    destination_code = code(destination)
    if not origin_code or not destination_code:
        return None
    return origin_code + "-" + destination_code
