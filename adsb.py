"""ADS-B.fi API helpers shared by the Tildagon Plane Radar app."""
API_BASE = "https://opendata.adsb.fi/api/v3/lat/{lat:.6f}/lon/{lon:.6f}/dist/{dist:.1f}"
SQUAWK_BASE = "https://opendata.adsb.fi/api/v2/sqk/{squawk}"
KM_PER_NM = 1.852
MAX_AIRCRAFT = 64
EMERGENCY_SQUAWKS = ("7500", "7600", "7700")
EMERGENCY_STATUSES = ("general", "minfuel", "nordo", "unlawful", "downed")

def build_url(lat, lon, radius_km):
    return API_BASE.format(lat=float(lat), lon=float(lon), dist=float(radius_km) / KM_PER_NM)

def build_squawk_url(squawk):
    value = str(squawk).strip()
    if len(value) != 4 or any(char not in "01234567" for char in value):
        raise ValueError("squawk must be four octal digits")
    return SQUAWK_BASE.format(squawk=value)

def _number(item, *keys):
    for key in keys:
        value = item.get(key)
        if isinstance(value, (int, float)): return float(value)
    return 0.0

def _trim(value, fallback=""):
    if not isinstance(value, str): return fallback
    return value.strip()

def _db_flags(item):
    value = item.get("dbFlags", item.get("db_flags", 0))
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0

def _starts_with_any(value, prefixes):
    for prefix in prefixes:
        if value.startswith(prefix):
            return True
    return False

def _altitude(item):
    value = item.get("alt_baro")
    if value == "ground": return "GND"
    if not isinstance(value, (int, float)): value = item.get("alt_geom")
    if not isinstance(value, (int, float)): return ""
    value = int(round(value))
    if abs(value) >= 1000: return "{}k".format(int(round(value / 1000.0)))
    return str(value)

def classify_aircraft(item):
    """Return a small display class from readsb/adsb.fi metadata.

    The feed's database military flag is the strongest signal. ADS-B emitter
    category A7 identifies rotorcraft; light/small and specialist categories
    are grouped as general aviation. Unknown aircraft stay ordinary civilian
    traffic so incomplete feeds never hide a target.
    """
    flags = _db_flags(item)
    if flags & 1:
        return "military"

    category = _trim(item.get("category")).upper()
    if category == "A7":
        return "helicopter"
    if category in ("A1", "A2", "B1", "B2", "B3", "B4", "B5", "B6"):
        return "ga"
    return "civilian"

def classify_attention(item):
    """Identify traffic worth a gentle visual/LED cue.

    readsb's database flags provide authoritative military and interesting
    markers. UK emergency-service callsigns provide deliberately narrow
    fallbacks; unknown traffic is never guessed from its colour or type.
    """
    callsign = (_trim(item.get("flight")) or _trim(item.get("callsign")))
    callsign = callsign.upper().replace(" ", "")
    registration = (_trim(item.get("r")) or _trim(item.get("registration")))
    registration = registration.upper().replace(" ", "")
    emergency = _trim(item.get("emergency"), "none").lower()
    flags = _db_flags(item)

    if emergency == "lifeguard" or _starts_with_any(
        callsign, ("HLE", "HELIMED")
    ):
        return "air_ambulance"
    if (
        _starts_with_any(callsign, ("UKP", "UKPOL", "POLICE", "NPAS"))
        or registration.startswith("G-POL")
        or registration == "G-NPAS"
    ):
        return "police"
    if flags & 1:
        return "military"
    if flags & 2:
        return "interesting"
    return ""

def needs_emergency_focus(item):
    """Separate genuine emergency states from the non-emergency lifeguard cue."""
    squawk = _trim(item.get("squawk"))[:4]
    emergency = _trim(item.get("emergency"), "none").lower()
    return squawk in EMERGENCY_SQUAWKS or emergency in EMERGENCY_STATUSES

def parse_aircraft(payload, show_ground=False, max_aircraft=MAX_AIRCRAFT):
    result = []
    if not isinstance(payload, dict): return result
    raw = payload.get("ac")
    if not isinstance(raw, list): return result
    for plane in raw:
        if len(result) >= max_aircraft: break
        if not isinstance(plane, dict): continue
        lat, lon = plane.get("lat"), plane.get("lon")
        if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)): continue
        if plane.get("alt_baro") == "ground" and not show_ground: continue
        callsign = _trim(plane.get("flight")) or _trim(plane.get("hex"), "?")
        category = _trim(plane.get("category")).upper()[:2]
        db_flags = _db_flags(plane)
        attention = classify_attention(plane)
        parsed = {
            "lat": float(lat), "lon": float(lon),
            "icao": _trim(plane.get("hex")),
            "squawk": _trim(plane.get("squawk"))[:4],
            "emergency": _trim(plane.get("emergency"), "none").lower(),
            "heading": _number(plane, "true_heading", "mag_heading", "track", "dir"),
            "track": _number(plane, "track", "true_heading", "mag_heading", "dir"),
            "speed": _number(plane, "gs", "tas", "ias"),
            "callsign": callsign[:9], "type": _trim(plane.get("t"))[:6], "alt": _altitude(plane),
            "category": category, "db_flags": db_flags,
            "kind": classify_aircraft(plane),
        }
        # Preserve the extra key only for the small minority of relevant
        # aircraft; this keeps normal radar records lean on MicroPython.
        if attention:
            parsed["attention"] = attention
        result.append(parsed)
    return result
