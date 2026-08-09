"""Helpers for mirroring radar traffic onto Tildagon's 12 RGB LEDs."""
import math

LED_COUNT = 12
DEGREES_PER_LED = 360.0 / LED_COUNT


def bearing_from_offsets(east_km, north_km):
    """Return true-style bearing degrees (north=0, east=90), or None."""
    if abs(east_km) < 1e-9 and abs(north_km) < 1e-9:
        return None
    return math.degrees(math.atan2(east_km, north_km)) % 360.0


def led_index_for_bearing(bearing_deg):
    """Map a bearing to Tildagon LED number 1..12.

    The physical LED pairs follow the six button sectors: LEDs 12/1 are at
    the top, then 2/3 clockwise around the badge. Each LED therefore covers
    a 30-degree radar sector.
    """
    bearing = float(bearing_deg) % 360.0
    return int(bearing / DEGREES_PER_LED) % LED_COUNT + 1


def led_index_from_offsets(east_km, north_km):
    bearing = bearing_from_offsets(east_km, north_km)
    if bearing is None:
        return None
    return led_index_for_bearing(bearing)


def max_rgb(existing, new):
    """Combine LED layers without dimming a brighter radar feature."""
    return tuple(max(existing[i], new[i]) for i in range(3))
