"""Plane Radar for Tildagon.

This is a MicroPython/Tildagon port of MatixYo/ESP32-Plane-Radar.  The first
commit establishes the round radar UI and native Tildagon controls; later
commits add live ADS-B data and persistent configuration.
"""

import math
import app

from events.input import Buttons, BUTTON_TYPES

try:
    from .radar_math import heading_vector, offset_km, radar_xy, rim_xy
except ImportError:
    from radar_math import heading_vector, offset_km, radar_xy, rim_xy

GRID_RADIUS = 94
RIM_RADIUS = 108
RING_LABELS_KM = (5, 10, 15, 25)
DEFAULT_RANGE_INDEX = 1
BACKGROUND = (0.01, 0.025, 0.07)
GRID = (0.0, 0.34, 0.20)
GRID_DIM = (0.0, 0.20, 0.13)
WHITE = (0.94, 0.96, 1.0)
RED = (1.0, 0.18, 0.16)
MAGENTA = (1.0, 0.12, 0.66)
YELLOW = (1.0, 0.78, 0.12)

def _outer_range_km(ring_label_km):
    return float(ring_label_km) * 4.0 / 3.0

class PlaneRadarApp(app.App):
    def __init__(self):
        super().__init__()
        self.button_states = Buttons(self)
        self.range_index = DEFAULT_RANGE_INDEX
        self.aircraft = []
        self.status = "Tildagon port"

    @property
    def ring_label_km(self):
        return RING_LABELS_KM[self.range_index]

    @property
    def outer_km(self):
        return _outer_range_km(self.ring_label_km)

    def update(self, delta):
        if self.button_states.get(BUTTON_TYPES["RIGHT"]):
            self.range_index = (self.range_index + 1) % len(RING_LABELS_KM)
            self.button_states.clear()
        elif self.button_states.get(BUTTON_TYPES["CANCEL"]):
            self.button_states.clear()
            self.minimise()

    def _draw_grid(self, ctx):
        ctx.rgb(*BACKGROUND).rectangle(-120, -120, 240, 240).fill()
        ctx.line_width = 1
        for idx, radius in enumerate((24, 47, 71, GRID_RADIUS)):
            colour = GRID if idx == 2 else GRID_DIM
            ctx.rgb(*colour).arc(0, 0, radius, 0, 2 * math.pi, True).stroke()
        ctx.rgb(*GRID_DIM).begin_path()
        ctx.move_to(-GRID_RADIUS, 0); ctx.line_to(GRID_RADIUS, 0)
        ctx.move_to(0, -GRID_RADIUS); ctx.line_to(0, GRID_RADIUS); ctx.stroke()
        ctx.rgb(*WHITE); ctx.font_size = 10
        ctx.move_to(-3, -103).text("N"); ctx.move_to(-3, 110).text("S")
        ctx.move_to(101, 3).text("E"); ctx.move_to(-109, 3).text("W")
        ctx.font_size = 8; ctx.rgb(*GRID).move_to(73, -4).text(str(self.ring_label_km) + "km")
        ctx.rgb(*WHITE).arc(0, 0, 2, 0, 2 * math.pi, True).fill()

    def _draw_aircraft(self, ctx, item):
        lat, lon = item.get("lat"), item.get("lon")
        if lat is None or lon is None: return
        x, y, distance = radar_xy(item.get("center_lat", 0.0), item.get("center_lon", 0.0), lat, lon, self.outer_km, GRID_RADIUS)
        if distance > self.outer_km:
            east, north, _ = offset_km(item.get("center_lat", 0.0), item.get("center_lon", 0.0), lat, lon)
            x, y = rim_xy(east, north, RIM_RADIUS)
            ctx.rgb(*RED).arc(x, y, 2.2, 0, 2 * math.pi, True).fill(); return
        speed = item.get("speed", 0.0) or 0.0
        vector_len = 6.0 + min(float(speed), 600.0) / 600.0 * 12.0
        vdx, vdy = heading_vector(item.get("track", 0.0), vector_len)
        ctx.rgb(*MAGENTA).begin_path(); ctx.move_to(x, y); ctx.line_to(x + vdx, y + vdy); ctx.stroke()
        fdx, fdy = heading_vector(item.get("heading", 0.0), 5.0)
        rdx, rdy = -fdy * 0.6, fdx * 0.6; bx, by = x - fdx * 0.8, y - fdy * 0.8
        ctx.rgb(*RED).begin_path(); ctx.move_to(x + fdx, y + fdy); ctx.line_to(bx + rdx, by + rdy); ctx.line_to(bx - rdx, by - rdy); ctx.close_path(); ctx.fill()

    def draw(self, ctx):
        ctx.save(); self._draw_grid(ctx)
        for item in self.aircraft: self._draw_aircraft(ctx, item)
        if self.status:
            ctx.font_size = 8; ctx.rgb(*YELLOW); width = ctx.text_width(self.status); ctx.move_to(-width / 2, 95).text(self.status)
        ctx.restore()

__app_export__ = PlaneRadarApp
