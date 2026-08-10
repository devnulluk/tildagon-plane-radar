"""Live ADS-B aircraft radar for the Tildagon round display."""
import math
import time

import app
import requests
import settings
from app_components import TextDialog
from events.input import Buttons, BUTTON_TYPES, ButtonDownEvent, ButtonUpEvent
from system.eventbus import eventbus
from system.patterndisplay.events import PatternDisable, PatternEnable
from tildagonos import tildagonos

try:
    from .radar_math import heading_vector, offset_km, radar_xy, rim_xy
    from .adsb import build_url, parse_aircraft
    from .location_provider import get_best_position
    from .led_radar import led_index_for_bearing, max_rgb
    from .spaceagon import (
        angular_distance,
        bearing_from_offsets,
        calibrated_heading,
        is_spaceagon,
        raw_compass_heading,
        relative_bearing,
        rotate_screen_xy,
        touch_bearing,
        zoom_index,
    )
    from .instructions_qr import draw_qr
    from .postcode import POSTCODE_URL, normalise_postcode, postcode_coordinates
    from .wifi_location import get_wifi_position
except ImportError:
    from radar_math import heading_vector, offset_km, radar_xy, rim_xy
    from adsb import build_url, parse_aircraft
    from location_provider import get_best_position
    from led_radar import led_index_for_bearing, max_rgb
    from spaceagon import (
        angular_distance,
        bearing_from_offsets,
        calibrated_heading,
        is_spaceagon,
        raw_compass_heading,
        relative_bearing,
        rotate_screen_xy,
        touch_bearing,
        zoom_index,
    )
    from instructions_qr import draw_qr
    from postcode import POSTCODE_URL, normalise_postcode, postcode_coordinates
    from wifi_location import get_wifi_position

CONFIG_KEY = "plane_radar_tildagon"
GRID_RADIUS = 94
RIM_RADIUS = 108
RING_LABELS_KM = (5, 10, 15, 25)
DEFAULT_RANGE_INDEX = 1
POLL_INTERVAL_MS = 5000
LED_UPDATE_MS = 100
COMPASS_UPDATE_MS = 200
NORMAL_SPLASH_MS = 1800
FIRST_SPLASH_MS = 5000
SELECTION_MS = 7000
KM_PER_MILE = 1.609344
DEFAULT_CONFIG = {
    "lat": None,
    "lon": None,
    "range_index": DEFAULT_RANGE_INDEX,
    "use_miles": False,
    "intro_seen": False,
    "heading_up": False,
    "compass_zero": None,
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
CYAN = (0.2, 0.82, 1.0)


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
        self.location_choice = 0

        self.spaceagon = is_spaceagon()
        self.heading_up = bool(self.config.get("heading_up", False)) and self.spaceagon
        self.compass_zero = self.config.get("compass_zero")
        self.compass_heading = None
        self.compass_elapsed = COMPASS_UPDATE_MS
        self.pending_touch_bearing = None
        self.pending_zoom = 0
        self.pending_joy_action = None
        self.joy_fire_started = None
        self.suppress_confirm = False
        if self.spaceagon:
            eventbus.on(ButtonDownEvent, self._handle_spaceagon_down, self)
            eventbus.on(ButtonUpEvent, self._handle_spaceagon_up, self)

        self.selected_item = None
        self.selected_distance = None
        self.selected_bearing = None
        self.selection_elapsed = 0

        self.first_run = not bool(self.config.get("intro_seen", False))
        self.view = "splash"
        self.splash_elapsed = 0

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
                "heading_up": self.heading_up,
                "compass_zero": self.compass_zero,
            }
        )
        _save_config(self.config)

    def _mark_intro_seen(self):
        if not self.config.get("intro_seen", False):
            self.config["intro_seen"] = True
            _save_config(self.config)

    def _finish_splash(self):
        self._mark_intro_seen()
        self.view = "radar"
        self.button_states.clear()
        if self.center_lat is None or self.center_lon is None:
            self.status = "No GPS - OK manual"
        elif self.location_source == "gps":
            self.status = "GPS position"
        elif self.location_source == "wifi":
            self.status = "Wi-Fi estimate"
        else:
            self.status = "Manual position"

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
        if self.setup_stage == "postcode":
            self._dialog_cleanup()
            postcode = normalise_postcode(text)
            if len(postcode) < 5 or len(postcode) > 7:
                self.setup_stage = None
                self.status = "Invalid UK postcode"
                return
            response = None
            try:
                self.status = "Looking up postcode..."
                response = requests.get(POSTCODE_URL.format(postcode))
                coords = postcode_coordinates(response.json())
                if coords is None:
                    self.status = "Postcode not found"
                    self.setup_stage = None
                    return
                self._save_manual_location(coords[0], coords[1])
                self.status = "Postcode location saved"
            except Exception as exc:
                print("plane-radar: postcode lookup failed:", exc)
                self.setup_stage = None
                self.status = "Postcode lookup failed"
            finally:
                if response is not None:
                    try:
                        response.close()
                    except Exception:
                        pass
            return
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
            self._save_manual_location(self.pending_lat, value)
            self.pending_lat = None
            self.status = "Manual location saved"

    def _save_manual_location(self, lat, lon):
        self.manual_lat = lat
        self.manual_lon = lon
        self._dialog_cleanup()
        self.setup_stage = None
        self._persist_preferences()
        self.center_lat = lat
        self.center_lon = lon
        self.location_source = "manual"
        self.location_provider = None
        self.poll_elapsed = POLL_INTERVAL_MS

    def _open_setup_dialog_if_needed(self):
        if self.dialog is not None or self.setup_stage is None:
            return
        if self.setup_stage == "postcode":
            prompt = "UK POSTCODE\n(e.g. CM7 1AA)"
        elif self.setup_stage == "lat":
            prompt = "LATITUDE\n(e.g. 51.5074)"
        else:
            prompt = "LONGITUDE\n(e.g. -0.1278)"
        self.dialog = TextDialog(
            prompt,
            self,
            masked=False,
            on_complete=self._complete_location,
            on_cancel=self._cancel_location,
        )

    def _refresh_position(self, startup=False):
        """Try GPS, then Wi-Fi; retain the saved manual centre on failure."""
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

        result = get_wifi_position(requests)
        if result is not None:
            lat, lon, accuracy = result
            self.center_lat = lat
            self.center_lon = lon
            self.location_source = "wifi"
            self.location_provider = "BeaconDB"
            self.status = "Wi-Fi ~{}m".format(int(round(accuracy)))
            self.poll_elapsed = POLL_INTERVAL_MS
            return True

        if self.center_lat is not None and self.center_lon is not None:
            self.status = "Auto location failed - kept location"
            return False

        if self.manual_lat is not None and self.manual_lon is not None:
            self.center_lat = self.manual_lat
            self.center_lon = self.manual_lon
            self.location_source = "manual"
            self.location_provider = None
            self.status = "Using manual location"
            self.poll_elapsed = POLL_INTERVAL_MS
            return False

        self.location_source = "none"
        self.location_provider = None
        self.status = "No auto location - OK manual"
        return False

    def _handle_spaceagon_down(self, event):
        if self.view != "radar" or self.dialog is not None:
            return
        name = getattr(event.button, "name", "")
        bearing = touch_bearing(name)
        if bearing is not None:
            self.pending_touch_bearing = bearing
            return
        if name == "LEFTPROX":
            self.pending_zoom = -1
            return
        if name == "RIGHTPROX":
            self.pending_zoom = 1
            return
        if "JOYFIRE" in name and self.joy_fire_started is None:
            self.joy_fire_started = time.ticks_ms()
            self.suppress_confirm = True

    def _handle_spaceagon_up(self, event):
        if self.view != "radar" or self.dialog is not None:
            return
        name = getattr(event.button, "name", "")
        if "JOYFIRE" not in name or self.joy_fire_started is None:
            return
        held_ms = time.ticks_diff(time.ticks_ms(), self.joy_fire_started)
        self.joy_fire_started = None
        self.pending_joy_action = "calibrate" if held_ms >= 1200 else "toggle"
        self.suppress_confirm = True

    def _read_compass_raw(self):
        if not self.spaceagon:
            return None
        try:
            import imu

            return raw_compass_heading(imu.mag_read())
        except Exception as exc:
            print("plane-radar: compass read failed:", exc)
            return None

    def _update_compass(self):
        raw = self._read_compass_raw()
        if raw is None:
            self.compass_heading = None
            return
        self.compass_heading = calibrated_heading(raw, self.compass_zero or 0.0)

    def _toggle_heading_up(self):
        if not self.spaceagon:
            return
        if self.heading_up:
            self.heading_up = False
            self.status = "North-up"
            self._persist_preferences()
            return
        if self.compass_zero is None:
            self.status = "Hold FIRE facing north to calibrate"
            return
        self._update_compass()
        if self.compass_heading is None:
            self.status = "Compass unavailable"
            return
        self.heading_up = True
        self.status = "Heading-up"
        self._persist_preferences()

    def _calibrate_compass(self):
        raw = self._read_compass_raw()
        if raw is None:
            self.status = "Compass unavailable"
            return
        self.compass_zero = raw
        self.compass_heading = 0.0
        self.heading_up = True
        self.status = "Compass calibrated - heading-up"
        self._persist_preferences()

    def _display_heading(self):
        if self.heading_up and self.compass_heading is not None:
            return self.compass_heading
        return 0.0

    def _process_spaceagon_actions(self):
        if not self.spaceagon:
            return

        if self.pending_zoom:
            new_index = zoom_index(
                self.range_index, self.pending_zoom, len(RING_LABELS_KM)
            )
            self.pending_zoom = 0
            if new_index != self.range_index:
                self.range_index = new_index
                self._persist_preferences()
                self.poll_elapsed = POLL_INTERVAL_MS
                self.status = "Range " + self._range_label()

        if self.pending_touch_bearing is not None:
            target = self.pending_touch_bearing
            self.pending_touch_bearing = None
            self._select_aircraft_by_touch(target)

        if self.pending_joy_action is not None:
            action = self.pending_joy_action
            self.pending_joy_action = None
            if action == "calibrate":
                self._calibrate_compass()
            else:
                self._toggle_heading_up()

        if self.suppress_confirm and self.button_states.get(BUTTON_TYPES["CONFIRM"]):
            self.button_states.clear()
        if self.suppress_confirm and self.joy_fire_started is None:
            self.suppress_confirm = False

    def _select_aircraft_by_touch(self, relative_touch_bearing):
        if self.center_lat is None or self.center_lon is None:
            self.status = "Set location first"
            return
        if not self.aircraft:
            self.status = "No aircraft to inspect"
            return

        target_true = (relative_touch_bearing + self._display_heading()) % 360.0
        best = None
        best_key = None
        for item in self.aircraft:
            lat = item.get("lat")
            lon = item.get("lon")
            if lat is None or lon is None:
                continue
            east, north, distance = offset_km(
                self.center_lat, self.center_lon, lat, lon
            )
            bearing = bearing_from_offsets(east, north)
            if bearing is None:
                continue
            difference = angular_distance(bearing, target_true)
            key = (difference, distance)
            if best_key is None or key < best_key:
                best_key = key
                best = (item, distance, bearing)

        if best is None or best_key[0] > 30.0:
            self.selected_item = None
            clock = int(round(relative_touch_bearing / 30.0)) or 12
            self.status = "No traffic near {} o'clock".format(clock)
            return

        self.selected_item, self.selected_distance, self.selected_bearing = best
        self.selection_elapsed = 0
        self.status = "Traffic selected"

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

        display_heading = self._display_heading()
        if self.center_lat is not None and self.center_lon is not None:
            for item in self.aircraft:
                lat = item.get("lat")
                lon = item.get("lon")
                if lat is None or lon is None:
                    continue
                east, north, distance = offset_km(
                    self.center_lat, self.center_lon, lat, lon
                )
                bearing = bearing_from_offsets(east, north)
                if bearing is None:
                    continue
                led_bearing = relative_bearing(bearing, display_heading)
                led = led_index_for_bearing(led_bearing)
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
            self.selected_item = None
        except Exception as exc:
            print("plane-radar: ADS-B fetch failed:", exc)
            self.status = "ADS-B fetch failed"
        finally:
            if response is not None:
                try:
                    response.close()
                except Exception:
                    pass

    def _handle_splash_input(self, delta):
        self.splash_elapsed += delta
        duration = FIRST_SPLASH_MS if self.first_run else NORMAL_SPLASH_MS
        if self.button_states.get(BUTTON_TYPES["CONFIRM"]):
            self.button_states.clear()
            self._mark_intro_seen()
            self.view = "instructions"
            return
        if self.button_states.get(BUTTON_TYPES["CANCEL"]):
            self._finish_splash()
            return
        if self.splash_elapsed >= duration:
            self._finish_splash()

    def _handle_instructions_input(self):
        if (
            self.button_states.get(BUTTON_TYPES["CONFIRM"])
            or self.button_states.get(BUTTON_TYPES["CANCEL"])
        ):
            self.button_states.clear()
            self._finish_splash()

    def _handle_location_setup_input(self):
        if self.button_states.get(BUTTON_TYPES["LEFT"]):
            self.location_choice = (self.location_choice - 1) % 3
            self.button_states.clear()
        elif self.button_states.get(BUTTON_TYPES["RIGHT"]):
            self.location_choice = (self.location_choice + 1) % 3
            self.button_states.clear()
        elif self.button_states.get(BUTTON_TYPES["CONFIRM"]):
            self.button_states.clear()
            self.view = "radar"
            if self.location_choice == 0:
                self._refresh_position(startup=False)
            elif self.location_choice == 1:
                self.setup_stage = "postcode"
            else:
                self.pending_lat = None
                self.setup_stage = "lat"
        elif self.button_states.get(BUTTON_TYPES["CANCEL"]):
            self.button_states.clear()
            self.view = "radar"

    def update(self, delta):
        if not self.leds_active:
            self._acquire_leds()

        if not self.position_checked:
            self.position_checked = True
            self._refresh_position(startup=True)

        self.led_elapsed += delta
        if self.led_elapsed >= LED_UPDATE_MS:
            self.led_elapsed = 0
            self._update_radar_leds()

        if self.spaceagon:
            self.compass_elapsed += delta
            if self.compass_elapsed >= COMPASS_UPDATE_MS:
                self.compass_elapsed = 0
                if self.heading_up:
                    self._update_compass()

        if self.view == "splash":
            self._handle_splash_input(delta)
            return
        if self.view == "instructions":
            self._handle_instructions_input()
            return
        if self.view == "location_setup":
            self._handle_location_setup_input()
            return

        self._open_setup_dialog_if_needed()
        if self.dialog is not None:
            return

        self._process_spaceagon_actions()

        if self.selected_item is not None:
            self.selection_elapsed += delta
            if self.selection_elapsed >= SELECTION_MS:
                self.selected_item = None

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
            self.location_choice = 0
            self.view = "location_setup"
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

    def _draw_cardinal(self, ctx, label, true_bearing, radius=103):
        display_bearing = relative_bearing(true_bearing, self._display_heading())
        x, y = heading_vector(display_bearing, radius)
        width = ctx.text_width(label)
        ctx.move_to(x - width / 2, y + 3).text(label)

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
        ctx.font_size = 9
        self._draw_cardinal(ctx, "N", 0)
        self._draw_cardinal(ctx, "E", 90)
        self._draw_cardinal(ctx, "S", 180)
        self._draw_cardinal(ctx, "W", 270)

        ctx.font_size = 8
        ctx.rgb(*GRID).move_to(73, -4).text(self._range_label())
        ctx.rgb(*WHITE).arc(0, 0, 2, 0, 2 * math.pi, True).fill()

        if self.heading_up and self.compass_heading is not None:
            text = "HDG {:03d}".format(int(round(self.compass_heading)) % 360)
            width = ctx.text_width(text)
            ctx.rgb(*CYAN).move_to(-width / 2, -116).text(text)

    def _screen_point_for_aircraft(self, item):
        lat = item.get("lat")
        lon = item.get("lon")
        if lat is None or lon is None:
            return None
        x, y, distance = radar_xy(
            self.center_lat,
            self.center_lon,
            lat,
            lon,
            self.outer_km,
            GRID_RADIUS,
        )
        if self.heading_up and self.compass_heading is not None:
            x, y = rotate_screen_xy(x, y, self.compass_heading)
        return x, y, distance

    def _draw_aircraft(self, ctx, item):
        lat = item.get("lat")
        lon = item.get("lon")
        if lat is None or lon is None:
            return

        point = self._screen_point_for_aircraft(item)
        if point is None:
            return
        x, y, distance = point

        if distance > self.outer_km:
            east, north, _ = offset_km(
                self.center_lat, self.center_lon, lat, lon
            )
            x, y = rim_xy(east, north, RIM_RADIUS)
            if self.heading_up and self.compass_heading is not None:
                x, y = rotate_screen_xy(x, y, self.compass_heading)
            ctx.rgb(*RED).arc(x, y, 2.2, 0, 2 * math.pi, True).fill()
            return

        display_heading = self._display_heading()
        speed = item.get("speed", 0.0) or 0.0
        vector_len = 6.0 + min(float(speed), 600.0) / 600.0 * 12.0
        vdx, vdy = heading_vector(
            relative_bearing(item.get("track", 0.0), display_heading), vector_len
        )
        ctx.rgb(*MAGENTA).begin_path()
        ctx.move_to(x, y)
        ctx.line_to(x + vdx, y + vdy)
        ctx.stroke()

        fdx, fdy = heading_vector(
            relative_bearing(item.get("heading", 0.0), display_heading), 5.0
        )
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

        if item is self.selected_item:
            ctx.rgb(*YELLOW)
            ctx.line_width = 1.5
            ctx.arc(x, y, 8, 0, 2 * math.pi, True).stroke()
            ctx.line_width = 1

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

    def _distance_text(self, distance_km):
        if distance_km is None:
            return ""
        if self.use_miles:
            return "{:.1f}mi".format(distance_km / KM_PER_MILE)
        return "{:.1f}km".format(distance_km)

    def _draw_selection(self, ctx):
        if self.selected_item is None:
            return
        callsign = self.selected_item.get("callsign", "?")
        type_code = self.selected_item.get("type", "")
        alt = self.selected_item.get("alt", "")
        speed = self.selected_item.get("speed", 0.0) or 0.0
        line1 = callsign + (("  " + type_code) if type_code else "")
        line2 = "{}  {}  {}kt".format(
            alt or "alt ?",
            self._distance_text(self.selected_distance),
            int(round(float(speed))),
        )
        ctx.rgba(0, 0, 0, 0.78).rectangle(-94, 48, 188, 39).fill()
        ctx.font_size = 9
        ctx.rgb(*YELLOW)
        w1 = ctx.text_width(line1)
        ctx.move_to(-w1 / 2, 60).text(line1)
        ctx.font_size = 8
        ctx.rgb(*WHITE)
        w2 = ctx.text_width(line2)
        ctx.move_to(-w2 / 2, 74).text(line2)

    def _draw_location_source(self, ctx):
        ctx.font_size = 7
        if self.location_source == "gps":
            ctx.rgb(*GPS_TEXT).move_to(-105, -88).text("GPS")
        elif self.location_source == "wifi":
            ctx.rgb(*CYAN).move_to(-105, -88).text("WIFI")
        elif self.location_source == "manual":
            ctx.rgb(*ALT_TEXT).move_to(-105, -88).text("MAN")
        else:
            ctx.rgb(*YELLOW).move_to(-105, -88).text("NO LOC")

        if self.spaceagon:
            ctx.rgb(*CYAN).move_to(77, -88).text("SP")
            if self.heading_up:
                ctx.rgb(*CYAN).move_to(76, -78).text("HDG")

    def _draw_splash(self, ctx):
        ctx.rgb(*BACKGROUND).rectangle(-120, -120, 240, 240).fill()
        ctx.line_width = 1
        for radius in (30, 55, 82):
            ctx.rgb(*GRID_DIM).arc(0, 0, radius, 0, 2 * math.pi, True).stroke()
        ctx.rgb(*GRID_DIM).begin_path()
        ctx.move_to(-82, 0)
        ctx.line_to(82, 0)
        ctx.move_to(0, -82)
        ctx.line_to(0, 82)
        ctx.stroke()

        sweep = (self.splash_elapsed % 1800) * 360.0 / 1800.0
        sx, sy = heading_vector(sweep, 82)
        ctx.rgb(0.05, 0.9, 0.38)
        ctx.line_width = 2
        ctx.begin_path().move_to(0, 0).line_to(sx, sy).stroke()
        ctx.line_width = 1
        for bearing, radius in ((40, 58), (132, 43), (276, 70)):
            px, py = heading_vector(bearing, radius)
            ctx.rgb(*RED).arc(px, py, 2.4, 0, 2 * math.pi, True).fill()

        ctx.font_size = 18
        ctx.rgb(*WHITE)
        title = "PLANE RADAR"
        ctx.move_to(-ctx.text_width(title) / 2, -104).text(title)
        ctx.font_size = 8
        subtitle = "LIVE ADS-B / TILDAGON"
        ctx.rgb(*GPS_TEXT).move_to(-ctx.text_width(subtitle) / 2, -84).text(subtitle)

        if self.first_run:
            draw_qr(ctx, 0, 23, 2)
            ctx.font_size = 8
            prompt = "Click OK for instructions"
            ctx.rgb(*YELLOW).move_to(-ctx.text_width(prompt) / 2, 78).text(prompt)
        else:
            ctx.font_size = 10
            text = "Scanning the skies..."
            ctx.rgb(*YELLOW).move_to(-ctx.text_width(text) / 2, 12).text(text)

    def _draw_instructions(self, ctx):
        ctx.rgb(*BACKGROUND).rectangle(-120, -120, 240, 240).fill()
        ctx.font_size = 13
        ctx.rgb(*WHITE)
        title = "PLANE RADAR HELP"
        ctx.move_to(-ctx.text_width(title) / 2, -108).text(title)
        ctx.font_size = 8
        text = "Scan for controls & setup"
        ctx.rgb(*GPS_TEXT).move_to(-ctx.text_width(text) / 2, -91).text(text)
        draw_qr(ctx, 0, -12, 3)
        ctx.font_size = 8
        hint = "OK / Back to radar"
        ctx.rgb(*YELLOW).move_to(-ctx.text_width(hint) / 2, 92).text(hint)

    def _draw_location_setup(self, ctx):
        ctx.rgb(*BACKGROUND).rectangle(-120, -120, 240, 240).fill()
        ctx.font_size = 20
        ctx.rgb(*WHITE)
        title = "SET LOCATION"
        ctx.move_to(-ctx.text_width(title) / 2, -92).text(title)
        options = ("AUTO GPS / WI-FI", "UK POSTCODE", "COORDINATES")
        ctx.font_size = 17
        choice = options[self.location_choice]
        ctx.rgb(*GPS_TEXT).move_to(-ctx.text_width(choice) / 2, -18).text(choice)
        ctx.font_size = 11
        hint = "LEFT / RIGHT"
        ctx.rgb(*ALT_TEXT).move_to(-ctx.text_width(hint) / 2, 30).text(hint)
        hint = "OK TO SELECT"
        ctx.rgb(*YELLOW).move_to(-ctx.text_width(hint) / 2, 52).text(hint)
        ctx.font_size = 9
        hint = "BACK TO CANCEL"
        ctx.rgb(*ALT_TEXT).move_to(-ctx.text_width(hint) / 2, 83).text(hint)

    def draw(self, ctx):
        ctx.save()
        if self.view == "splash":
            self._draw_splash(ctx)
            ctx.restore()
            return
        if self.view == "instructions":
            self._draw_instructions(ctx)
            ctx.restore()
            return
        if self.view == "location_setup":
            self._draw_location_setup(ctx)
            ctx.restore()
            return

        self._draw_grid(ctx)
        if self.center_lat is not None and self.center_lon is not None:
            for item in self.aircraft:
                self._draw_aircraft(ctx, item)
        self._draw_location_source(ctx)
        self._draw_selection(ctx)
        if self.status:
            ctx.font_size = 8
            ctx.rgb(*YELLOW)
            width = ctx.text_width(self.status)
            ctx.move_to(-width / 2, 95).text(self.status)
        ctx.restore()
        if self.dialog is not None:
            self.dialog.draw(ctx)


__app_export__ = PlaneRadarApp
