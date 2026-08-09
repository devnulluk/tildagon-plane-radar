"""ADS-B.fi API helpers shared by the Tildagon Plane Radar app."""
API_BASE = "https://opendata.adsb.fi/api/v3/lat/{lat:.6f}/lon/{lon:.6f}/dist/{dist:.1f}"
KM_PER_NM = 1.852
MAX_AIRCRAFT = 64

def build_url(lat, lon, radius_km):
    return API_BASE.format(lat=float(lat), lon=float(lon), dist=float(radius_km) / KM_PER_NM)

def _number(item, *keys):
    for key in keys:
        value = item.get(key)
        if isinstance(value, (int, float)): return float(value)
    return 0.0

def _trim(value, fallback=""):
    if not isinstance(value, str): return fallback
    return value.strip()

def _altitude(item):
    value = item.get("alt_baro")
    if value == "ground": return "GND"
    if not isinstance(value, (int, float)): value = item.get("alt_geom")
    if not isinstance(value, (int, float)): return ""
    value = int(round(value))
    if abs(value) >= 1000: return "{}k".format(int(round(value / 1000.0)))
    return str(value)

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
        result.append({
            "lat": float(lat), "lon": float(lon),
            "heading": _number(plane, "true_heading", "mag_heading", "track", "dir"),
            "track": _number(plane, "track", "true_heading", "mag_heading", "dir"),
            "speed": _number(plane, "gs", "tas", "ias"),
            "callsign": callsign[:9], "type": _trim(plane.get("t"))[:6], "alt": _altitude(plane),
        })
    return result
