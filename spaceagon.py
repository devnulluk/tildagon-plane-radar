"""Optional Spaceagon helpers for Plane Radar.

Everything in here degrades safely on a 2024 Tildagon. The app detects the
2026 frontboard at runtime and only enables touch/proximity/compass features
when it is actually present.
"""
import math

SPACEAGON_FAMILY = 0x2600
SPACEAGON_MASK = 0xFF00


def is_spaceagon():
    try:
        from frontboards.utils import detect_frontboard

        return (int(detect_frontboard()) & SPACEAGON_MASK) == SPACEAGON_FAMILY
    except Exception:
        return False


def touch_bearing(button_name):
    """Map TOUCH01..TOUCH12 clock positions to true-style degrees.

    TOUCH12 is the top/north of the badge, TOUCH03 is right/east, TOUCH06 is
    bottom/south and TOUCH09 is left/west.
    """
    if not isinstance(button_name, str) or not button_name.startswith("TOUCH"):
        return None
    try:
        index = int(button_name[-2:])
    except (TypeError, ValueError):
        return None
    if index < 1 or index > 12:
        return None
    return float((index % 12) * 30)


def bearing_from_offsets(east_km, north_km):
    if abs(east_km) < 1e-9 and abs(north_km) < 1e-9:
        return None
    return math.degrees(math.atan2(east_km, north_km)) % 360.0


def relative_bearing(true_bearing, heading):
    return (float(true_bearing) - float(heading or 0.0)) % 360.0


def angular_distance(a, b):
    return abs((float(a) - float(b) + 180.0) % 360.0 - 180.0)


def rotate_screen_xy(x, y, heading_degrees):
    """Rotate a north-up screen point into heading-up coordinates."""
    angle = math.radians(float(heading_degrees or 0.0))
    c = math.cos(angle)
    s = math.sin(angle)
    return x * c + y * s, -x * s + y * c


def raw_compass_heading(mag):
    """Return an uncalibrated horizontal magnetometer heading.

    Exact axis orientation is intentionally corrected by the user calibration
    offset in the app because Spaceagon hardware still needs physical testing.
    """
    if not isinstance(mag, (tuple, list)) or len(mag) < 2:
        return None
    try:
        x = float(mag[0])
        y = float(mag[1])
    except (TypeError, ValueError):
        return None
    if abs(x) < 1e-12 and abs(y) < 1e-12:
        return None
    return math.degrees(math.atan2(y, x)) % 360.0


def calibrated_heading(raw_heading, zero_offset):
    if raw_heading is None:
        return None
    return (float(raw_heading) - float(zero_offset or 0.0)) % 360.0


def parse_manual_bearing(value):
    """Parse 0..359 degrees, with N/NORTH as an explicit north-up reset."""
    text = str(value).strip().upper()
    if text in ("N", "NORTH"):
        return None
    try:
        bearing = float(text)
    except (TypeError, ValueError):
        raise ValueError("bearing must be 0..359 or N")
    if bearing < 0.0 or bearing >= 360.0:
        raise ValueError("bearing must be 0..359")
    return bearing


def zoom_index(current, direction, count):
    if count <= 0:
        return current
    return max(0, min(int(count) - 1, int(current) + int(direction)))
