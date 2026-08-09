"""Live ADS-B aircraft radar for the Tildagon round display."""
import math

import app
import requests
import settings
from app_components import TextDialog
from events.input import Buttons, BUTTON_TYPES
from system.eventbus import eventbus
from system.patterndisplay.events import PatternDisable, PatternEnable
from tildagonos import tildagonos

try:
    from .radar_math import heading_vector, offset_km, radar_xy, rim_xy
    from .adsb import build_url, parse_aircraft
    from .location_provider import get_best_position
    from .led_radar import led_index_from_offsets, max_rgb
except ImportError:
    from radar_math import heading_vector, offset_km, radar_xy, rim_xy
    from adsb import build_url, parse_aircraft
    from location_provider import get_best_position
    from led_radar import led_index_from_offsets, max_rgb

CONFIG_KEY = "plane_radar_tildagon"
GRID_RADIUS = 94
RIM_RADIUS = 108
RING_LABELS_KM = (5, 10, 15, 25)
DEFAULT_RANGE_INDEX = 1
POLL_INTERVAL_MS = 5000
LED_UPDATE_MS = 100
KM_PER_MILE = 1.609344
DEFAULT_CONFIG = {
    "lat": None,
    "lon": None,
    "range_index": DEFAULT_RANGE_INDEX,
    "use_miles": False,
}

BACKGROUND = (0.01, 0.025, 0.07)
GRID = (0.0, 0.34, 0.20)
GRID_DIM = (0.0, 0.20, 0.13)
WHITE = (0.94, 0.96, 1.0)
RED = (1.0, 0.18, 0.16)
MAGENTA = (1.0, 0.12, 0.66)
YELLOW = (1.0, 0.78, 0.12)
ALT_TEXT = (0.72, 0.75, 0.82)
GPS_TEXT = (0.25, 1.0, 0.45)


def _load_config():
    stored = settings.get(CONFIG_KEY)
    config = DEFAULT_CONFIG.copy()
    if isinstance(stored, dict):
        config.update(stored)
    index = config.get("range_index", DEFAULT_RANGE_INDEX)
    if not isinstance(index, int) or index < 0 or index >= len(RING_LABELS_KM):
        config["range_index"] = DEFAULT_RANGE_INDEX
    return config


def _save_config(config):
    settings.set(CONFIG_KEY, config)
    settings.save()


def _outer_range_km(ring_label_km):
    return float(ring_label_km) * 4.0 / 3.0


class PlaneRadarApp(app.App):
    def __init__(self):
        super().__init__()
        self.button_states = Buttons(self)
        self.config = _load_config()
        self.range_index = self.config["range_index"]
        self.manual_lat = self.config.get("lat")
        self.manual_lon = self.config.get("lon")
        self.center_lat = self.manual_lat
        self.center_lon = self.manual_lon
        self.location_source = (
            "manual"
            if self.manual_lat is not None and self.manual_lon is not None
            else "none"
        )
        self.location_provider = None
        self.position_checked = False
        self.use_miles = bool(self.config.get("use_miles", False))
        self.aircraft = []
        self.status = "Checking GPS..."
        self.poll_elapsed = POLL_INTERVAL_MS
        self.dialog = None
        self.setup_stage = None
        self.pending_lat = None
        self.led_elapsed = LED_UPDATE_MS
        self.sweep_led = 1
        self.leds_active = False
        self._acquire_leds()

    @property
    def ring_label_km(self):
        return RING_LABELS_KM[self.range_index]

    @property
    def outer_km(self):
        return _outer_range_km(self.ring_label_km)

    def _persist_preferences(self):
        self.config.update(
            {
                "lat": self.manual_lat,
                "lon": self.manual_lon,
                "range_index": self.range_index,
                "use_miles": self.use_miles,
            }
        )
        _save_config(self.config)

    def _dialog_cleanup(self):
        if self.dialog is not None:
            try:
                self.dialog._cleanup()
            except Exception:
                pass
            self.dialog = None

    def _cancel_location(self):
        self._dialog_cleanup()
        self.setup_stage = None
        self.status = (
            "No location - DOWN GPS"
            if self.center_lat is None or self.center_lon is None
            else "Location unchanged"
        )

    def _complete_location(self):
        text = self.dialog.text.strip() if self.dialog is not None else ""
        try:
            value = float(text)
        except Exception:
            self._dialog_cleanup()
            self.status = "Invalid coordinate"
            return

        if self.setup_stage == "lat":
            if value < -90.0 or value > 90.0:
                self._dialog_cleanup()
                self.status = "Latitude -90..90"
                return
            self.pending_lat = value
            self._dialog_cleanup()
            self.setup_stage = "lon"
            return

        if self.setup_stage == "lon":
            if value < -180.0 or value > 180.0:
                self._dialog_cleanup()
                self.status = "Longitude -180..180"
                return
            self.manual_lat = self.pending_lat
            self.manual_lon = value
            self.pending_lat = None
            self._dialog_cleanup()
            self.setup_stage = None
            self._persist_preferences()

            # Manual entry explicitly switches the current radar centre. GPS can
            # be requested again at any time with DOWN.
            self.center_lat = self.manual_lat
            self.center_lon = self.manual_lon
            self.location_source = "manual"
            self.location_provider = None
            self.poll_elapsed = POLL_INTERVAL_MS
            self.status = "Manual location saved"

    def _open_setup_dialog_if_needed(self):
        if self.dialog is not None or self.setup_stage is None:
            return
        prompt = (
            "Radar latitude\n(e.g. 51.5074)"
            if self.setup_stage == "lat"
            else "Radar longitude\n(e.g. -0.1278)"
        )
        self.dialog = TextDialog(
            prompt,
            self,
            masked=False,
            on_complete=self._complete_location,
            on_cancel=self._cancel_location,
        )

    def _refresh_position(self, startup=False):
        """Try GPS once; retain the existing centre when no new fix exists."""
        result = get_best_position()
        if result is not None:
            lat, lon, provider_name = result
            self.center_lat = lat
            self.center_lon = lon
            self.location_source = "gps"
            self.location_provider = provider_name
            self.status = "GPS lock" if startup else "GPS updated"
            self.poll_elapsed = POLL_INTERVAL_MS
            return True

        # A failed refresh must not erase a perfectly useful existing centre.
        if self.center_lat is not None and self.center_lon is not None:
            self.status = "No GPS fix - kept location"
            return False

        if self.manual_lat is not None and self.manual_lon is not None:
            self.center_lat = self.manual_lat
            self.center_lon = self.manual_lon
            self.location_source = "manual"
            self.location_provider = None
            self.status = "No GPS - manual location"
            self.poll_elapsed = POLL_INTERVAL_MS
            return False

        self.location_source = "none"
        self.location_provider = None
        self.status = "No GPS - OK manual"
        return False

    def _acquire_leds(self):
        if self.leds_active:
            return
        eventbus.emit(PatternDisable())
        try:
            tildagonos.set_led_power(True)
        except Exception:
            pass
        self.leds_active = True
        self.led_elapsed = LED_UPDATE_MS

    def _release_leds(self):
        if not self.leds_active:
            return
        try:
            for led in range(1, 13):
                tildagonos.leds[led] = (0, 0, 0)
            tildagonos.leds.write()
        except Exception:
            pass
        eventbus.emit(PatternEnable())
        self.leds_active = False

    def _update_radar_leds(self):
        if not self.leds_active:
            return

        frame = [(0, 0, 0) for _ in range(12)]
        for offset, colour in (
            (0, (0, 52, 12)),
            (-1, (0, 18, 5)),
            (-2, (0, 6, 2)),
        ):
            index = (self.sweep_led - 1 + offset) % 12
            frame[index] = max_rgb(frame[index], colour)

        if self.center_lat is not None and self.center_lon is not None:
            for item in self.aircraft:
                lat = item.get("lat")
                lon = item.get("lon")
                if lat is None or lon is None:
                    continue
                east, north, distance = offset_km(
                    self.center_lat, self.center_lon, lat, lon
                )
                led = led_index_from_offsets(east, north)
                if led is None:
                    continue
                if distance <= self.outer_km:
                    closeness = 1.0 - min(distance / self.outer_km, 1.0)
                    colour = (
                        int(120 + 135 * closeness),
                        4,
                        int(28 + 62 * closeness),
                    )
                else:
                    colour = (42, 0, 24)
                frame[led - 1] = max_rgb(frame[led - 1], colour)

        if self.location_source == "gps":
            frame[0] = max_rgb(frame[0], (0, 10, 28))
            frame[11] = max_rgb(frame[11], (0, 10, 28))

        try:
            for led, colour in enumerate(frame, 1):
                tildagonos.leds[led] = colour
            tildagonos.leds.write()
        except Exception as exc:
            print("plane-radar: LED update failed:", exc)
            self._release_leds()

        self.sweep_led = self.sweep_led % 12 + 1

    def minimise(self):
        self._release_leds()
        super().minimise()

    def terminate(self, restore_pattern=False):
        self._release_leds()
        super().terminate(restore_pattern=restore_pattern)

    def _fetch_aircraft(self):
        if self.center_lat is None or self.center_lon is None:
            return
        response = None
        try:
            import wifi

            if not wifi.status():
                self.status = "Connecting Wi-Fi..."
                wifi.connect()
                if not wifi.wait():
                    self.status = "Wi-Fi unavailable"
                    return
            response = requests.get(
                build_url(self.center_lat, self.center_lon, self.outer_km * 1.25)
            )
            status_code = getattr(response, "status_code", 200)
            if status_code != 200:
                self.status = "ADS-B HTTP {}".format(status_code)
                return
            self.aircraft = parse_aircraft(response.json())
            self.status = "{} aircraft".format(len(self.aircraft))
        except Exception as exc:
            print("plane-radar: ADS-B fetch failed:", exc)
            self.status = "ADS-B fetch failed"
        finally:
            if response is not None:
                try:
                    response.close()
                except Exception:
                    pass

    def update(self, delta):
        if not self.leds_active:
            self._acquire_leds()

        self._open_setup_dialog_if_needed()
        if self.dialog is not None:
            return

        # GPS is intentionally sampled once when the app starts. Users can
        # request a fresh fix with DOWN; we do not continuously move the radar
        # centre underneath them.
        if not self.position_checked:
            self.position_checked = True
            self._refresh_position(startup=True)

        self.led_elapsed += delta
        if self.led_elapsed >= LED_UPDATE_MS:
            self.led_elapsed = 0
            self._update_radar_leds()

        if self.button_states.get(BUTTON_TYPES["RIGHT"]):
            self.range_index = (self.range_index + 1) % len(RING_LABELS_KM)
            self._persist_preferences()
            self.poll_elapsed = POLL_INTERVAL_MS
            self.button_states.clear()
        elif self.button_states.get(BUTTON_TYPES["LEFT"]):
            self.poll_elapsed = POLL_INTERVAL_MS
            self.button_states.clear()
        elif self.button_states.get(BUTTON_TYPES["UP"]):
            self.use_miles = not self.use_miles
            self._persist_preferences()
            self.button_states.clear()
        elif self.button_states.get(BUTTON_TYPES["DOWN"]):
            self._refresh_position(startup=False)
            self.button_states.clear()
        elif self.button_states.get(BUTTON_TYPES["CONFIRM"]):
            self.setup_stage = "lat"
            self.pending_lat = None
            self.button_states.clear()
        elif self.button_states.get(BUTTON_TYPES["CANCEL"]):
            self.button_states.clear()
            self.minimise()
            return

        if self.center_lat is None or self.center_lon is None:
            return

        self.poll_elapsed += delta
        if self.poll_elapsed >= POLL_INTERVAL_MS:
            self.poll_elapsed = 0
            self._fetch_aircraft()

    def _range_label(self):
        if self.use_miles:
            return str(int(round(self.ring_label_km / KM_PER_MILE))) + "mi"
        return str(self.ring_label_km) + "km"

    def _draw_grid(self, ctx):
        ctx.rgb(*BACKGROUND).rectangle(-120, -120, 240, 240).fill()
        ctx.line_width = 1
        for idx, radius in enumerate((24, 47, 71, GRID_RADIUS)):
            ctx.rgb(*(GRID if idx == 2 else GRID_DIM)).arc(
                0, 0, radius, 0, 2 * math.pi, True
            ).stroke()
        ctx.rgb(*GRID_DIM).begin_path()
        ctx.move_to(-GRID_RADIUS, 0)
        ctx.line_to(GRID_RADIUS, 0)
        ctx.move_to(0, -GRID_RADIUS)
        ctx.line_to(0, GRID_RADIUS)
        ctx.stroke()
        ctx.rgb(*WHITE)
        ctx.font_size = 10
        ctx.move_to(-3, -103).text("N")
        ctx.move_to(-3, 110).text("S")
        ctx.move_to(101, 3).text("E")
        ctx.move_to(-109, 3).text("W")
        ctx.font_size = 8
        ctx.rgb(*GRID).move_to(73, -4).text(self._range_label())
        ctx.rgb(*WHITE).arc(0, 0, 2, 0, 2 * math.pi, True).fill()

    def _draw_aircraft(self, ctx, item):
        lat = item.get("lat")
        lon = item.get("lon")
        if lat is None or lon is None:
            return

        x, y, distance = radar_xy(
            self.center_lat,
            self.center_lon,
            lat,
            lon,
            self.outer_km,
            GRID_RADIUS,
        )
        if distance > self.outer_km:
            east, north, _ = offset_km(
                self.center_lat, self.center_lon, lat, lon
            )
            x, y = rim_xy(east, north, RIM_RADIUS)
            ctx.rgb(*RED).arc(x, y, 2.2, 0, 2 * math.pi, True).fill()
            return

        speed = item.get("speed", 0.0) or 0.0
        vector_len = 6.0 + min(float(speed), 600.0) / 600.0 * 12.0
        vdx, vdy = heading_vector(item.get("track", 0.0), vector_len)
        ctx.rgb(*MAGENTA).begin_path()
        ctx.move_to(x, y)
        ctx.line_to(x + vdx, y + vdy)
        ctx.stroke()

        fdx, fdy = heading_vector(item.get("heading", 0.0), 5.0)
        rdx = -fdy * 0.6
        rdy = fdx * 0.6
        bx = x - fdx * 0.8
        by = y - fdy * 0.8
        ctx.rgb(*RED).begin_path()
        ctx.move_to(x + fdx, y + fdy)
        ctx.line_to(bx + rdx, by + rdy)
        ctx.line_to(bx - rdx, by - rdy)
        ctx.close_path()
        ctx.fill()

        label = item.get("callsign", "")
        alt = item.get("alt", "")
        if label:
            ctx.font_size = 7
            ctx.rgb(*WHITE)
            width = ctx.text_width(label)
            tx = x + 7 if x < 0 else x - 7 - width
            ty = y - 1
            ctx.move_to(tx, ty).text(label)
            if alt:
                alt_width = ctx.text_width(alt)
                ax = x + 7 if x < 0 else x - 7 - alt_width
                ctx.rgb(*ALT_TEXT).move_to(ax, ty + 8).text(alt)

    def _draw_location_source(self, ctx):
        ctx.font_size = 7
        if self.location_source == "gps":
            ctx.rgb(*GPS_TEXT).move_to(-105, -88).text("GPS")
        elif self.location_source == "manual":
            ctx.rgb(*ALT_TEXT).move_to(-105, -88).text("MAN")
        else:
            ctx.rgb(*YELLOW).move_to(-105, -88).text("NO LOC")

    def draw(self, ctx):
        ctx.save()
        self._draw_grid(ctx)
        if self.center_lat is not None and self.center_lon is not None:
            for item in self.aircraft:
                self._draw_aircraft(ctx, item)
        self._draw_location_source(ctx)
        if self.status:
            ctx.font_size = 8
            ctx.rgb(*YELLOW)
            width = ctx.text_width(self.status)
            ctx.move_to(-width / 2, 95).text(self.status)
        ctx.restore()
        if self.dialog is not None:
            self.dialog.draw(ctx)


__app_export__ = PlaneRadarApp
