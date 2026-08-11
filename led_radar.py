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


def pulse_level(now_ms, period_ms=2400, minimum=28):
    """Return a smooth integer pulse level from minimum to 100."""
    period_ms = max(2, int(period_ms))
    phase = int(now_ms) % period_ms
    half = period_ms // 2
    strength = half - abs(phase - half)
    return int(minimum) + strength * (100 - int(minimum)) // half


def red_chase_frame(count, now_ms, step_ms=90):
    """Build a fast twin red chase, distinct from a broad military sweep."""
    count = max(1, int(count))
    head = int(now_ms // max(1, int(step_ms))) % count
    frame = [(6, 0, 0) for _ in range(count)]
    for start in (head, (head + count // 2) % count):
        for offset, level in ((0, 180), (-1, 76), (-2, 26)):
            frame[(start + offset) % count] = (level, 0, 0)
    return frame


def colour_sweep_frame(count, now_ms, colour, step_ms=120):
    """Build a coloured sweep with a soft three-LED tail."""
    count = max(1, int(count))
    head = int(now_ms // max(1, int(step_ms))) % count
    red, green, blue = colour
    background = (red * 3 // 100, green * 3 // 100, blue * 3 // 100)
    frame = [background for _ in range(count)]
    for offset, strength in ((0, 100), (-1, 45), (-2, 16)):
        frame[(head + offset) % count] = (
            red * strength // 100,
            green * strength // 100,
            blue * strength // 100,
        )
    return frame


def cycled_colour_sweep_frame(
    count, colours, now_ms, colour_ms=1800, step_ms=120
):
    """Sweep each supplied colour in turn, returning black when none exist."""
    if not colours:
        return [(0, 0, 0) for _ in range(max(1, int(count)))]
    colour_ms = max(1, int(colour_ms))
    index = int(now_ms // colour_ms) % len(colours)
    within_colour = int(now_ms) % colour_ms
    return colour_sweep_frame(count, within_colour, colours[index], step_ms)
