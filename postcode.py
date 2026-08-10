"""Small, dependency-free UK postcode lookup helpers."""

POSTCODE_URL = "https://api.postcodes.io/postcodes/{}"


def normalise_postcode(value):
    """Return the compact uppercase form accepted by Postcodes.io."""
    return "".join(str(value or "").upper().split())


def format_postcode(value):
    """Return a compact postcode with the standard space before its last 3 chars."""
    compact = normalise_postcode(value)
    if len(compact) < 5:
        return compact
    return compact[:-3] + " " + compact[-3:]


def postcode_coordinates(payload):
    """Extract and validate latitude/longitude from a Postcodes.io response."""
    if not isinstance(payload, dict) or payload.get("status") != 200:
        return None
    result = payload.get("result")
    if not isinstance(result, dict):
        return None
    lat = result.get("latitude")
    lon = result.get("longitude")
    if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
        return None
    if not -90 <= lat <= 90 or not -180 <= lon <= 180:
        return None
    return float(lat), float(lon)
