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
    from .led_radar import (
        colour_sweep_frame,
        cycled_colour_sweep_frame,
        led_index_for_bearing,
        max_rgb,
        pulse_level,
        red_chase_frame,
        scale_rgb,
    )
    from .spaceagon import (
        angular_distance,
        bearing_from_offsets,
        calibrated_heading,
        is_spaceagon,
        parse_manual_bearing,
        raw_compass_heading,
        relative_bearing,
        rotate_screen_xy,
        touch_bearing,
        zoom_index,
    )
    from .instructions_qr import draw_qr
    from .postcode import (
        POSTCODE_URL,
        format_postcode,
        normalise_postcode,
        postcode_coordinates,
    )
    from .wifi_location import get_wifi_position
    from .route_lookup import build_route_lookup_url, parse_route_label
    from .hexpansion_cockpit import (
        HexpansionCockpit,
        KEYBOARD_BRIGHTNESS_LEVELS,
        LOGO_BRIGHTNESS_LEVELS,
        logo_port_label,
        next_logo_port,
        normalise_logo_port,
    )
except ImportError:
    from radar_math import heading_vector, offset_km, radar_xy, rim_xy
    from adsb import build_url, parse_aircraft
    from location_provider import get_best_position
    from led_radar import (
        colour_sweep_frame,
        cycled_colour_sweep_frame,
        led_index_for_bearing,
        max_rgb,
        pulse_level,
        red_chase_frame,
        scale_rgb,
    )
    from spaceagon import (
        angular_distance,
        bearing_from_offsets,
        calibrated_heading,
        is_spaceagon,
        parse_manual_bearing,
        raw_compass_heading,
        relative_bearing,
        rotate_screen_xy,
        touch_bearing,
        zoom_index,
    )
    from instructions_qr import draw_qr
    from postcode import (
        POSTCODE_URL,
        format_postcode,
        normalise_postcode,
        postcode_coordinates,
    )
    from wifi_location import get_wifi_position
    from route_lookup import build_route_lookup_url, parse_route_label
    from hexpansion_cockpit import (
        HexpansionCockpit,
        KEYBOARD_BRIGHTNESS_LEVELS,
        LOGO_BRIGHTNESS_LEVELS,
        logo_port_label,
        next_logo_port,
        normalise_logo_port,
    )

CONFIG_KEY = "plane_radar_tildagon"
GRID_RADIUS = 94
RIM_RADIUS = 108
RING_LABELS_KM = (2, 5, 10, 15)
DEFAULT_RANGE_INDEX = 2
RANGE_PROFILE = 2
POLL_INTERVAL_MS = 5000
LED_UPDATE_MS = 100
RADAR_OPTION_COUNT = 11
COMPASS_UPDATE_MS = 200
NORMAL_SPLASH_MS = 5000
FIRST_SPLASH_MS = 5000
SELECTION_MS = 7000
TRAIL_POINTS = 20
AIRCRAFT_LABEL_SIZE = 14
LOCATION_NOTICE_MS = 4500
DEMO_STAGE_MS = 3600
COARSE_LOCATION_METRES = 5000
KM_PER_MILE = 1.609344
DEFAULT_CONFIG = {
    "lat": None,
    "lon": None,
    "postcode": None,
    "range_index": DEFAULT_RANGE_INDEX,
    "range_profile": RANGE_PROFILE,
    "use_miles": False,
    "intro_seen": False,
    "heading_up": False,
    "compass_zero": None,
    "manual_bearing": None,
    "led_sweep": True,
    "led_sweep_brightness": 25,
    "hexpansion_fx": True,
    "keyboard_brightness": 100,
    "eeh_logo_brightness": 10,
    "eeh_logo_port": "auto",
}

BACKGROUND = (0.005, 0.045, 0.025)
GRID = (0.0, 0.62, 0.32)
GRID_DIM = (0.0, 0.34, 0.19)
WHITE = (0.94, 0.96, 1.0)
RED = (1.0, 0.18, 0.16)
MAGENTA = (1.0, 0.12, 0.66)
YELLOW = (1.0, 0.78, 0.12)
ALT_TEXT = (0.72, 0.75, 0.82)
GPS_TEXT = (0.25, 1.0, 0.45)
CYAN = (0.2, 0.82, 1.0)
POLICE_BLUE = (0.12, 0.42, 1.0)
INTERESTING = (1.0, 0.55, 0.08)
AIRCRAFT_COLOURS = (
    (0.25, 1.0, 0.15),
    (1.0, 0.18, 0.86),
    (0.12, 0.78, 1.0),
    (1.0, 0.86, 0.12),
    (1.0, 0.42, 0.12),
)
DEMO_STAGES = (
    {
        "title": "AIR AMBULANCE",
        "line1": "GREEN LED ALERT",
        "line2": "ROTOR = HELICOPTER",
        "callsign": "HLE72",
        "kind": "helicopter",
        "heading": 90,
        "attention": "air_ambulance",
        "colour": GPS_TEXT,
        "led": (0, 180, 45),
    },
    {
        "title": "POLICE",
        "line1": "BLUE LED ALERT",
        "line2": "ROTOR = HELICOPTER",
        "callsign": "UKP151",
        "kind": "helicopter",
        "heading": 90,
        "attention": "police",
        "colour": POLICE_BLUE,
        "led": (0, 55, 220),
    },
    {
        "title": "MILITARY",
        "line1": "RED LED ALERT",
        "line2": "DELTA = MILITARY",
        "callsign": "RFR01",
        "kind": "military",
        "heading": 90,
        "attention": "military",
        "colour": RED,
        "led": (220, 0, 15),
    },
    {
        "title": "INTERESTING",
        "line1": "AMBER HALO",
        "line2": "DATABASE-MARKED",
        "callsign": "VIP01",
        "kind": "civilian",
        "heading": 90,
        "attention": "interesting",
        "colour": INTERESTING,
        "led": (190, 90, 0),
    },
    {
        "title": "SQUAWK 7700",
        "line1": "GENERAL EMERGENCY",
        "line2": "TWIN RED CHASE",
        "callsign": "SIM7700",
        "kind": "civilian",
        "heading": 90,
        "attention": "emergency",
        "colour": RED,
        "led": (220, 0, 0),
        "emergency": True,
    },
)
DEMO_BACKGROUND_ITEM = {"kind": "civilian", "heading": 225}


def _load_config():
    stored = settings.get(CONFIG_KEY)
    config = DEFAULT_CONFIG.copy()
    if isinstance(stored, dict):
        config.update(stored)
        # The first close-range profile reused index 1, silently changing an
        # existing 10 km preference into 5 km. Restore a balanced 10 km view
        # once, while retaining explicit range changes made afterwards.
        if stored.get("range_profile") != RANGE_PROFILE:
            config["range_index"] = DEFAULT_RANGE_INDEX
            config["range_profile"] = RANGE_PROFILE
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
        self.manual_postcode = self.config.get("postcode")
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
        self.aircraft_trails = {}
        self.aircraft_trail_misses = {}
        self.route_cache = {}
        self.label_elapsed = 0
        self.screen_sweep_elapsed = 0
        self.status = "Checking GPS..."
        self.poll_elapsed = POLL_INTERVAL_MS
        self.dialog = None
        self.setup_stage = None
        self.pending_lat = None
        self.location_choice = 0
        self.pending_location_seed = ""
        self.location_notice = None
        self.location_notice_detail = None
        self.location_notice_elapsed = 0
        self.location_warning = False
        self.location_warning_choice = 0
        self.location_warning_saved = False
        self.wifi_accuracy = None

        self.spaceagon = is_spaceagon()
        self.manual_bearing = self.config.get("manual_bearing")
        if not isinstance(self.manual_bearing, (int, float)):
            self.manual_bearing = None
        elif self.manual_bearing < 0.0 or self.manual_bearing >= 360.0:
            self.manual_bearing = None
        else:
            self.manual_bearing = float(self.manual_bearing)
        self.heading_up = bool(self.config.get("heading_up", False)) and (
            self.spaceagon or self.manual_bearing is not None
        )
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
        self.demo_stage = 0
        self.demo_elapsed = 0
        self._splash_button_handler = self._handle_splash_button_down
        eventbus.on(ButtonDownEvent, self._splash_button_handler, self)

        self.led_elapsed = LED_UPDATE_MS
        self.sweep_led = 1
        self.led_sweep = bool(self.config.get("led_sweep", True))
        self.led_sweep_brightness = int(
            self.config.get("led_sweep_brightness", 25)
        )
        if self.led_sweep_brightness not in (25, 50, 75, 100):
            self.led_sweep_brightness = 25
        self.hexpansion_fx = bool(self.config.get("hexpansion_fx", True))
        # This intentionally uses a new key: older releases shared a dim 25%
        # level with the much brighter Logo.  Keyboard alerts now start at 100%.
        self.hexpansion_brightness = int(
            self.config.get("keyboard_brightness", 100)
        )
        if self.hexpansion_brightness not in KEYBOARD_BRIGHTNESS_LEVELS:
            self.hexpansion_brightness = 100
        self.eeh_logo_brightness = int(
            self.config.get("eeh_logo_brightness", 10)
        )
        if self.eeh_logo_brightness not in LOGO_BRIGHTNESS_LEVELS:
            self.eeh_logo_brightness = 10
        self.eeh_logo_port = normalise_logo_port(
            self.config.get("eeh_logo_port", "auto")
        )
        self.hexpansion_cockpit = HexpansionCockpit(
            self,
            enabled=self.hexpansion_fx,
            brightness=self.hexpansion_brightness,
            logo_brightness=self.eeh_logo_brightness,
            logo_port=self.eeh_logo_port,
        )
        self.leds_active = False
        self._acquire_leds()

    @property
    def ring_label_km(self):
        return RING_LABELS_KM[self.range_index]

    @property
    def outer_km(self):
        return _outer_range_km(self.ring_label_km)

    def _persist_preferences(self):
        if "hexpansion_brightness" in self.config:
            del self.config["hexpansion_brightness"]
        self.config.update(
            {
                "lat": self.manual_lat,
                "lon": self.manual_lon,
                "postcode": self.manual_postcode,
                "range_index": self.range_index,
                "use_miles": self.use_miles,
                "heading_up": self.heading_up,
                "compass_zero": self.compass_zero,
                "manual_bearing": self.manual_bearing,
                "led_sweep": self.led_sweep,
                "led_sweep_brightness": self.led_sweep_brightness,
                "hexpansion_fx": self.hexpansion_fx,
                "keyboard_brightness": self.hexpansion_brightness,
                "eeh_logo_brightness": self.eeh_logo_brightness,
                "eeh_logo_port": self.eeh_logo_port,
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
            self.status = "No GPS - press C"
        elif self.location_source == "gps":
            self.status = "GPS position"
        elif self.location_source == "wifi":
            self.status = "Wi-Fi estimate"
        else:
            self.status = "Manual position"

    def _handle_splash_button_down(self, event):
        """Open the manual or showcase while startup updates are busy."""
        if self.view != "splash":
            return
        if BUTTON_TYPES["RIGHT"] in event.button:
            self._start_traffic_demo()
            return
        if BUTTON_TYPES["CONFIRM"] not in event.button:
            return
        self.button_states.clear()
        self._mark_intro_seen()
        self.view = "instructions"

    def _start_traffic_demo(self):
        self.button_states.clear()
        self.view = "traffic_demo"
        self.demo_stage = 0
        self.demo_elapsed = 0

    def _handle_traffic_demo_input(self, delta):
        self.demo_elapsed += delta
        if self.button_states.get(BUTTON_TYPES["RIGHT"]):
            self.demo_stage = (self.demo_stage + 1) % len(DEMO_STAGES)
            self.demo_elapsed = 0
            self.button_states.clear()
        elif self.button_states.get(BUTTON_TYPES["LEFT"]):
            self.demo_stage = (self.demo_stage - 1) % len(DEMO_STAGES)
            self.demo_elapsed = 0
            self.button_states.clear()
        elif (
            self.button_states.get(BUTTON_TYPES["CONFIRM"])
            or self.button_states.get(BUTTON_TYPES["CANCEL"])
        ):
            self._finish_splash()
        elif self.demo_elapsed >= DEMO_STAGE_MS:
            self.demo_elapsed %= DEMO_STAGE_MS
            self.demo_stage = (self.demo_stage + 1) % len(DEMO_STAGES)

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
        # C and keyboard Enter both arrive as CONFIRM. Do not let the submit
        # event survive the dialog and immediately reopen Radar Options.
        self.button_states.clear()
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
                self._save_manual_location(
                    coords[0], coords[1], postcode=format_postcode(postcode)
                )
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
        if self.setup_stage == "bearing":
            self._dialog_cleanup()
            try:
                value = parse_manual_bearing(text)
            except ValueError:
                self.setup_stage = None
                self.status = "Bearing 0..359 or N"
                return
            if value is None:
                self.manual_bearing = None
                self.heading_up = False
                self.setup_stage = None
                self.status = "North-up"
                self._persist_preferences()
                return
            self.manual_bearing = value
            self.heading_up = True
            self.setup_stage = None
            self.status = "Bearing {:03d} degrees".format(int(round(value)) % 360)
            self._persist_preferences()
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

    def _save_manual_location(self, lat, lon, postcode=None):
        self.manual_lat = lat
        self.manual_lon = lon
        if postcode is not None:
            self.manual_postcode = postcode
        self._dialog_cleanup()
        self.setup_stage = None
        self._persist_preferences()
        self.center_lat = lat
        self.center_lon = lon
        self.location_source = "manual"
        self.location_provider = None
        self.view = "radar"
        self.poll_elapsed = POLL_INTERVAL_MS

    def _show_location_notice(self, title, detail):
        self.location_notice = title
        self.location_notice_detail = detail
        self.location_notice_elapsed = 0

    def _open_setup_dialog_if_needed(self):
        if self.dialog is not None or self.setup_stage is None:
            return
        if self.setup_stage == "postcode":
            prompt = "UK POSTCODE"
        elif self.setup_stage == "lat":
            prompt = "LATITUDE\n(e.g. 51.5074)"
        elif self.setup_stage == "bearing":
            prompt = "BADGE BEARING\n0-359 OR N"
        else:
            prompt = "LONGITUDE\n(e.g. -0.1278)"
        self.dialog = TextDialog(
            prompt,
            self,
            masked=False,
            on_complete=self._complete_location,
            on_cancel=self._cancel_location,
        )
        seed = self.pending_location_seed
        if not seed and self.setup_stage == "postcode":
            seed = self.manual_postcode or ""
        elif not seed and self.setup_stage == "bearing" and self.manual_bearing is not None:
            seed = str(int(round(self.manual_bearing)) % 360)
        if seed:
            self.dialog.text = seed
            self.pending_location_seed = ""

    def _refresh_position(self, startup=False):
        """Try GPS, then Wi-Fi; retain the saved manual centre on failure."""
        result = get_best_position()
        if result is not None:
            lat, lon, provider_name = result
            self.center_lat = lat
            self.center_lon = lon
            self.location_source = "gps"
            self.location_provider = provider_name
            self.location_warning_saved = False
            self.status = "GPS lock" if startup else "GPS updated"
            self._show_location_notice("GPS LOCATION", "READY")
            self.poll_elapsed = POLL_INTERVAL_MS
            return True

        result = get_wifi_position(requests)
        if result is not None:
            lat, lon, accuracy = result
            self.wifi_accuracy = accuracy
            self.status = "Wi-Fi ~{}m".format(int(round(accuracy)))
            if accuracy >= COARSE_LOCATION_METRES:
                self.location_warning = True
                self.location_warning_choice = 0
                self.location_notice = None
                if (
                    self.manual_postcode
                    and self.manual_lat is not None
                    and self.manual_lon is not None
                ):
                    self.center_lat = self.manual_lat
                    self.center_lon = self.manual_lon
                    self.location_source = "manual"
                    self.location_provider = None
                    self.location_warning_saved = True
                    self.status = "Wi-Fi rough - using " + self.manual_postcode
                else:
                    self.center_lat = lat
                    self.center_lon = lon
                    self.location_source = "wifi"
                    self.location_provider = "BeaconDB"
                    self.location_warning_saved = False
            else:
                self.center_lat = lat
                self.center_lon = lon
                self.location_source = "wifi"
                self.location_provider = "BeaconDB"
                self.location_warning_saved = False
                self._show_location_notice(
                    "WI-FI LOCATION", "ABOUT {}m".format(int(round(accuracy)))
                )
            self.poll_elapsed = POLL_INTERVAL_MS
            return True

        if self.center_lat is not None and self.center_lon is not None:
            self.status = "Auto location failed - kept location"
            self._show_location_notice("LOCATION KEPT", "AUTO FAILED")
            return False

        if self.manual_lat is not None and self.manual_lon is not None:
            self.center_lat = self.manual_lat
            self.center_lon = self.manual_lon
            self.location_source = "manual"
            self.location_provider = None
            self.status = "Using manual location"
            self._show_location_notice("MANUAL LOCATION", "AUTO FAILED")
            self.poll_elapsed = POLL_INTERVAL_MS
            return False

        self.location_source = "none"
        self.location_provider = None
        self.status = "No auto location - press C"
        self._show_location_notice("NO LOCATION", "PRESS C FOR MANUAL")
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
        if self.heading_up:
            self.heading_up = False
            self.status = "North-up"
            self._persist_preferences()
            return
        if self.manual_bearing is not None:
            self.heading_up = True
            self.status = "Bearing-up"
            self._persist_preferences()
            return
        if not self.spaceagon:
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
        self.manual_bearing = None
        self.heading_up = True
        self.status = "Compass calibrated - heading-up"
        self._persist_preferences()

    def _display_heading(self):
        if self.heading_up:
            if self.manual_bearing is not None:
                return self.manual_bearing
            if self.compass_heading is not None:
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
                self.status = "ZOOM " + self._range_label()

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
            self._update_hexpansion_lights(time.ticks_ms())
            return

        now_ms = time.ticks_ms()
        if self.view == "traffic_demo":
            stage = DEMO_STAGES[self.demo_stage]
            if stage.get("emergency"):
                frame = red_chase_frame(12, self.demo_elapsed)
            else:
                frame = colour_sweep_frame(12, self.demo_elapsed, stage["led"])
            try:
                for led, colour in enumerate(frame, 1):
                    tildagonos.leds[led] = colour
                tildagonos.leds.write()
            except Exception as exc:
                print("plane-radar: demo LED sweep failed:", exc)
                self._release_leds()
            self._update_hexpansion_lights(now_ms)
            return

        frame = [(0, 0, 0) for _ in range(12)]
        if self.led_sweep:
            for offset, colour in (
                (0, (0, 52, 12)),
                (-1, (0, 18, 5)),
                (-2, (0, 6, 2)),
            ):
                index = (self.sweep_led - 1 + offset) % 12
                frame[index] = max_rgb(
                    frame[index],
                    scale_rgb(colour, self.led_sweep_brightness),
                )

        display_heading = self._display_heading()
        attention_pulse = pulse_level(now_ms)
        attention_types = []
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
                attention = item.get("attention", "")
                if (
                    attention
                    and distance <= self.outer_km
                    and attention not in attention_types
                ):
                    attention_types.append(attention)
                if (
                    attention in ("air_ambulance", "police", "military")
                    and distance <= self.outer_km
                ):
                    base_colour = self._attention_led_colour(attention)
                    colour = tuple(
                        channel * attention_pulse // 100 for channel in base_colour
                    )
                    for neighbour in (-1, 1):
                        index = (led - 1 + neighbour) % 12
                        glow = tuple(channel * 24 // 100 for channel in colour)
                        frame[index] = max_rgb(frame[index], glow)
                elif distance <= self.outer_km:
                    closeness = 1.0 - min(distance / self.outer_km, 1.0)
                    colour = (
                        int(120 + 135 * closeness),
                        4,
                        int(28 + 62 * closeness),
                    )
                else:
                    colour = (42, 0, 24)
                frame[led - 1] = max_rgb(frame[led - 1], colour)

        if len(attention_types) > 1:
            ordered = [
                attention
                for attention in (
                    "air_ambulance",
                    "police",
                    "military",
                    "interesting",
                )
                if attention in attention_types
            ]
            colours = [self._attention_led_colour(item) for item in ordered]
            frame = cycled_colour_sweep_frame(12, colours, now_ms)

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

        self._update_hexpansion_lights(now_ms)
        self.sweep_led = self.sweep_led % 12 + 1

    def _update_hexpansion_lights(self, now_ms):
        """Use expansions for startup ambience and exceptional traffic only."""
        self.hexpansion_cockpit.configure(
            self.hexpansion_fx,
            self.hexpansion_brightness,
            self.eeh_logo_brightness,
            self.eeh_logo_port,
        )
        if self.view in ("splash", "instructions"):
            self.hexpansion_cockpit.show_startup(now_ms)
            return
        if self.view == "traffic_demo":
            stage = DEMO_STAGES[self.demo_stage]
            self.hexpansion_cockpit.show_demo(
                stage["led"], bool(stage.get("emergency")), self.demo_elapsed
            )
            return

        attention_colours = self._visible_attention_colours()
        if attention_colours:
            self.hexpansion_cockpit.show_highlight(
                attention_colours, False, now_ms
            )
        else:
            self.hexpansion_cockpit.show_idle(now_ms)

    def _visible_attention_colours(self):
        """Return unique special-traffic colours currently inside the radar."""
        attention_colours = []
        if self.center_lat is not None and self.center_lon is not None:
            for item in self.aircraft:
                lat = item.get("lat")
                lon = item.get("lon")
                if lat is None or lon is None:
                    continue
                _east, _north, distance = offset_km(
                    self.center_lat, self.center_lon, lat, lon
                )
                if distance > self.outer_km:
                    continue
                attention = item.get("attention", "")
                if attention:
                    alert_colour = self._attention_led_colour(attention)
                    if alert_colour not in attention_colours:
                        attention_colours.append(alert_colour)
        return attention_colours

    def minimise(self):
        self.hexpansion_cockpit.release()
        self._release_leds()
        super().minimise()

    def terminate(self, restore_pattern=False):
        self.hexpansion_cockpit.release()
        self._release_leds()
        try:
            eventbus.remove(
                ButtonDownEvent, self._splash_button_handler, self
            )
        except Exception:
            pass
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
            self._update_aircraft_trails()
            self.status = "ZOOM " + self._range_label()
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
        self._lookup_one_route()

    def _lookup_one_route(self):
        """Progressively fill a small, session-only route-label cache."""
        if getattr(self, "following", False):
            return
        if len(self.route_cache) >= 64:
            self.route_cache = {}
        candidate = None
        for item in self.aircraft:
            callsign = item.get("callsign", "")
            if (
                not callsign
                or callsign == item.get("icao")
                or callsign in self.route_cache
            ):
                continue
            point = self._screen_point_for_aircraft(item)
            if point is not None and point[2] <= self.outer_km:
                candidate = item
                break
        if candidate is None:
            return

        callsign = candidate["callsign"]
        response = None
        try:
            response = requests.get(build_route_lookup_url(callsign))
            status_code = getattr(response, "status_code", 200)
            if status_code == 200:
                self.route_cache[callsign] = parse_route_label(response.json()) or ""
            elif status_code == 404:
                self.route_cache[callsign] = ""
            else:
                print("plane-radar: route HTTP", status_code)
        except Exception as exc:
            print("plane-radar: route lookup failed:", exc)
        finally:
            if response is not None:
                try:
                    response.close()
                except Exception:
                    pass

    def _aircraft_key(self, item):
        return item.get("icao") or item.get("callsign")

    def _aircraft_colour(self, item):
        attention = item.get("attention", "")
        if attention == "air_ambulance":
            return GPS_TEXT
        if attention == "police":
            return POLICE_BLUE
        if attention == "military":
            return RED
        if attention == "interesting":
            return INTERESTING
        kind = item.get("kind", "civilian")
        if kind == "military":
            return MAGENTA
        if kind == "helicopter":
            return CYAN
        if kind == "ga":
            return YELLOW
        key = self._aircraft_key(item) or "?"
        index = sum(ord(char) for char in key) % len(AIRCRAFT_COLOURS)
        return AIRCRAFT_COLOURS[index]

    def _attention_led_colour(self, attention):
        if attention == "air_ambulance":
            return (0, 180, 45)
        if attention == "police":
            return (0, 55, 220)
        if attention == "military":
            return (220, 0, 15)
        return (190, 90, 0)

    def _update_aircraft_trails(self):
        active = set()
        for item in self.aircraft:
            key = self._aircraft_key(item)
            if not key:
                continue
            active.add(key)
            self.aircraft_trail_misses[key] = 0
            points = self.aircraft_trails.get(key, [])
            point = (item.get("lat"), item.get("lon"))
            if not points or points[-1] != point:
                points.append(point)
            self.aircraft_trails[key] = points[-TRAIL_POINTS:]
        for key in tuple(self.aircraft_trails):
            if key not in active:
                misses = self.aircraft_trail_misses.get(key, 0) + 1
                self.aircraft_trail_misses[key] = misses
                if misses > 3:
                    del self.aircraft_trails[key]
                    del self.aircraft_trail_misses[key]

    def _handle_splash_input(self, delta):
        self.splash_elapsed += delta
        duration = FIRST_SPLASH_MS if self.first_run else NORMAL_SPLASH_MS
        if self.button_states.get(BUTTON_TYPES["RIGHT"]):
            self._start_traffic_demo()
            return
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

    def _select_location_option(self):
        """Activate the highlighted Radar Options item."""
        self.button_states.clear()
        self.view = "radar"
        if self.location_choice == 0:
            self._refresh_position(startup=False)
        elif self.location_choice == 1:
            self.setup_stage = "postcode"
        elif self.location_choice == 2:
            self.pending_lat = None
            self.setup_stage = "lat"
        elif self.location_choice == 3:
            self.setup_stage = "bearing"
        elif self.location_choice == 4:
            self.led_sweep = not self.led_sweep
            self._persist_preferences()
            self.status = "LED sweep " + ("on" if self.led_sweep else "off")
        elif self.location_choice == 5:
            levels = (25, 50, 75, 100)
            index = levels.index(self.led_sweep_brightness)
            self.led_sweep_brightness = levels[(index + 1) % len(levels)]
            self._persist_preferences()
            self.status = "LED sweep {}%".format(self.led_sweep_brightness)
        elif self.location_choice == 6:
            self.hexpansion_fx = not self.hexpansion_fx
            self._persist_preferences()
            self.hexpansion_cockpit.configure(
                self.hexpansion_fx,
                self.hexpansion_brightness,
                self.eeh_logo_brightness,
                self.eeh_logo_port,
            )
            self.status = "Hexpansion effects " + (
                "on" if self.hexpansion_fx else "off"
            )
        elif self.location_choice == 7:
            levels = KEYBOARD_BRIGHTNESS_LEVELS
            index = levels.index(self.hexpansion_brightness)
            self.hexpansion_brightness = levels[(index + 1) % len(levels)]
            self._persist_preferences()
            self.hexpansion_cockpit.configure(
                self.hexpansion_fx,
                self.hexpansion_brightness,
                self.eeh_logo_brightness,
                self.eeh_logo_port,
            )
            self.status = "Hexpansion lights {}%".format(
                self.hexpansion_brightness
            )
        elif self.location_choice == 8:
            levels = LOGO_BRIGHTNESS_LEVELS
            index = levels.index(self.eeh_logo_brightness)
            self.eeh_logo_brightness = levels[(index + 1) % len(levels)]
            self._persist_preferences()
            self.hexpansion_cockpit.configure(
                self.hexpansion_fx,
                self.hexpansion_brightness,
                self.eeh_logo_brightness,
                self.eeh_logo_port,
            )
            self.status = "EEH Logo lights {}%".format(
                self.eeh_logo_brightness
            )
        elif self.location_choice == 9:
            self.eeh_logo_port = next_logo_port(self.eeh_logo_port)
            self._persist_preferences()
            self.hexpansion_cockpit.configure(
                self.hexpansion_fx,
                self.hexpansion_brightness,
                self.eeh_logo_brightness,
                self.eeh_logo_port,
            )
            self.status = "EEH Logo " + logo_port_label(self.eeh_logo_port)
        else:
            self._start_traffic_demo()

    def _handle_location_setup_input(self):
        if (
            self.button_states.get(BUTTON_TYPES["LEFT"])
            or self.button_states.get(BUTTON_TYPES["UP"])
        ):
            self.location_choice = (
                self.location_choice - 1
            ) % RADAR_OPTION_COUNT
            self.button_states.clear()
        elif (
            self.button_states.get(BUTTON_TYPES["RIGHT"])
            or self.button_states.get(BUTTON_TYPES["DOWN"])
        ):
            self.location_choice = (
                self.location_choice + 1
            ) % RADAR_OPTION_COUNT
            self.button_states.clear()
        elif self.button_states.get(BUTTON_TYPES["CONFIRM"]):
            self._select_location_option()
        elif self.button_states.get(BUTTON_TYPES["CANCEL"]):
            self.button_states.clear()
            self.view = "radar"

    def update(self, delta):
        self.label_elapsed = (self.label_elapsed + delta) % 6000
        # Network polling is synchronous on the badge. Do not let a slow poll
        # turn the next frame into a large, visible sweep-angle jump.
        animation_delta = min(delta, 80)
        self.screen_sweep_elapsed = (
            self.screen_sweep_elapsed + animation_delta
        ) % 2400
        if not self.leds_active:
            self._acquire_leds()

        self.led_elapsed += delta
        if self.led_elapsed >= LED_UPDATE_MS:
            self.led_elapsed = 0
            self._update_radar_leds()

        if self.spaceagon:
            self.compass_elapsed += delta
            if self.compass_elapsed >= COMPASS_UPDATE_MS:
                self.compass_elapsed = 0
                if self.heading_up and self.manual_bearing is None:
                    self._update_compass()

        if self.view == "splash":
            self._handle_splash_input(delta)
            return
        if self.view == "instructions":
            self._handle_instructions_input()
            return
        if self.view == "traffic_demo":
            self._handle_traffic_demo_input(delta)
            return
        if self.view == "location_setup":
            self._handle_location_setup_input()
            return

        if self.location_warning:
            if self.location_warning_saved:
                if (
                    self.button_states.get(BUTTON_TYPES["CONFIRM"])
                    or self.button_states.get(BUTTON_TYPES["CANCEL"])
                ):
                    self.button_states.clear()
                    self.location_warning = False
                    self.poll_elapsed = POLL_INTERVAL_MS
                return
            if (
                self.button_states.get(BUTTON_TYPES["LEFT"])
                or self.button_states.get(BUTTON_TYPES["UP"])
            ):
                self.location_warning_choice = 0
                self.button_states.clear()
            elif (
                self.button_states.get(BUTTON_TYPES["RIGHT"])
                or self.button_states.get(BUTTON_TYPES["DOWN"])
            ):
                self.location_warning_choice = 1
                self.button_states.clear()
            elif self.button_states.get(BUTTON_TYPES["CONFIRM"]):
                self.button_states.clear()
                self.location_warning = False
                if self.location_warning_choice == 1:
                    self.location_choice = 1
                    self.view = "location_setup"
                else:
                    self.poll_elapsed = POLL_INTERVAL_MS
            return

        # Let the splash render first, then wait for Wi-Fi and run the complete
        # GPS -> Wi-Fi -> manual startup sequence exactly once.
        if not self.position_checked:
            self.position_checked = True
            self._refresh_position(startup=True)

        if self.location_notice is not None:
            self.location_notice_elapsed += delta
            confirm = self.button_states.get(BUTTON_TYPES["CONFIRM"])
            if confirm and (self.center_lat is None or self.center_lon is None):
                # On a failed startup, OK is an action, not merely a dismiss:
                # go directly to the useful manual postcode fallback.
                self.location_notice = None
                self.location_notice_detail = None
                self.setup_stage = "postcode"
                self.button_states.clear()
            elif (
                self.location_notice_elapsed >= LOCATION_NOTICE_MS
                or confirm
                or self.button_states.get(BUTTON_TYPES["CANCEL"])
            ):
                self.location_notice = None
                self.location_notice_detail = None
                self.button_states.clear()

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
            self.status = "ZOOM " + self._range_label()
            self.button_states.clear()
        elif self.button_states.get(BUTTON_TYPES["DOWN"]):
            self._refresh_position(startup=False)
            self.button_states.clear()
        elif self.button_states.get(BUTTON_TYPES["CONFIRM"]):
            if self.center_lat is None or self.center_lon is None:
                self.setup_stage = "postcode"
            else:
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

        if self.heading_up:
            prefix = "BRG" if self.manual_bearing is not None else "HDG"
            text = "{} {:03d}".format(
                prefix, int(round(self._display_heading())) % 360
            )
            width = ctx.text_width(text)
            ctx.rgb(*CYAN).move_to(-width / 2, -116).text(text)

    def _draw_idle_sweep(self, ctx):
        """Keep an empty radar visibly alive without adding bitmap assets."""
        if self.aircraft or getattr(self, "following", False):
            return
        sweep = self.screen_sweep_elapsed * 360.0 / 2400.0
        for offset, strength in ((-16, 0.22), (-8, 0.48), (0, 1.0)):
            dx, dy = heading_vector(sweep + offset, GRID_RADIUS - 2)
            colour = (
                GRID[0] * strength,
                GRID[1] * strength,
                GRID[2] * strength,
            )
            ctx.rgb(*colour)
            ctx.line_width = 1.0 if offset else 1.8
            ctx.begin_path()
            ctx.move_to(0, 0)
            ctx.line_to(dx, dy)
            ctx.stroke()
        ctx.rgb(*GRID).arc(dx, dy, 2.0, 0, 2 * math.pi, True).fill()
        ctx.line_width = 1

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
        if self.heading_up:
            x, y = rotate_screen_xy(x, y, self._display_heading())
        return x, y, distance

    def _draw_aircraft_symbol(self, ctx, x, y, item, colour, display_heading):
        """Draw a feed-classified, rotation-aware aircraft marker."""
        direction = relative_bearing(item.get("heading", 0.0), display_heading)
        fdx, fdy = heading_vector(direction, 1.0)
        rdx, rdy = -fdy, fdx
        kind = item.get("kind", "civilian")
        ctx.rgb(*colour)

        if kind == "helicopter":
            # Circular cabin, tail boom and a crosswise main rotor.
            ctx.line_width = 1.4
            ctx.arc(x, y, 3.2, 0, 2 * math.pi, True).stroke()
            ctx.begin_path()
            ctx.move_to(x - fdx * 3, y - fdy * 3)
            ctx.line_to(x - fdx * 8, y - fdy * 8)
            ctx.move_to(x + rdx * 6, y + rdy * 6)
            ctx.line_to(x - rdx * 6, y - rdy * 6)
            ctx.move_to(x - fdx * 8 + rdx * 2, y - fdy * 8 + rdy * 2)
            ctx.line_to(x - fdx * 8 - rdx * 2, y - fdy * 8 - rdy * 2)
            ctx.stroke()
            ctx.line_width = 1
            return

        if kind == "ga":
            # A small hollow diamond is legible beside the filled jet shapes.
            ctx.line_width = 1.5
            ctx.begin_path()
            ctx.move_to(x + fdx * 7, y + fdy * 7)
            ctx.line_to(x + rdx * 4, y + rdy * 4)
            ctx.line_to(x - fdx * 5, y - fdy * 5)
            ctx.line_to(x - rdx * 4, y - rdy * 4)
            ctx.close_path()
            ctx.stroke()
            ctx.line_width = 1
            return

        if kind == "military":
            # A broad delta with a notched tail.
            ctx.begin_path()
            ctx.move_to(x + fdx * 8, y + fdy * 8)
            ctx.line_to(x - fdx * 2 + rdx * 6, y - fdy * 2 + rdy * 6)
            ctx.line_to(x - fdx * 1, y - fdy * 1)
            ctx.line_to(x - fdx * 2 - rdx * 6, y - fdy * 2 - rdy * 6)
            ctx.close_path()
            ctx.fill()
            return

        # Ordinary civilian/commercial traffic keeps the familiar triangle.
        ctx.begin_path()
        ctx.move_to(x + fdx * 7, y + fdy * 7)
        ctx.line_to(x - fdx * 5 + rdx * 5, y - fdy * 5 + rdy * 5)
        ctx.line_to(x - fdx * 5 - rdx * 5, y - fdy * 5 - rdy * 5)
        ctx.close_path()
        ctx.fill()

    def _draw_aircraft(self, ctx, item):
        lat = item.get("lat")
        lon = item.get("lon")
        if lat is None or lon is None:
            return

        point = self._screen_point_for_aircraft(item)
        if point is None:
            return
        x, y, distance = point
        colour = self._aircraft_colour(item)
        if getattr(self, "following", False):
            # Nearby traffic remains useful context around a followed target,
            # but must never compete with the centred aircraft or its data.
            colour = (
                colour[0] * 0.30,
                colour[1] * 0.30,
                colour[2] * 0.30,
            )

        if distance > self.outer_km:
            east, north, _ = offset_km(
                self.center_lat, self.center_lon, lat, lon
            )
            x, y = rim_xy(east, north, RIM_RADIUS)
            if self.heading_up:
                x, y = rotate_screen_xy(x, y, self._display_heading())
            ctx.rgb(*BACKGROUND).arc(x, y, 4.2, 0, 2 * math.pi, True).fill()
            ctx.rgb(*colour).arc(x, y, 3.1, 0, 2 * math.pi, True).fill()
            return

        trail = self.aircraft_trails.get(self._aircraft_key(item), [])
        screen_trail = []
        for trail_lat, trail_lon in trail:
            trail_point = self._screen_point_for_aircraft(
                {"lat": trail_lat, "lon": trail_lon}
            )
            if trail_point is not None and trail_point[2] <= self.outer_km:
                screen_trail.append(trail_point[:2])
        for index in range(1, len(screen_trail)):
            # Retain the age fade, but keep older track segments readable on
            # the tiny physical LCD (roughly halfway back towards full colour).
            old_strength = 0.22 + (
                0.68 * index / max(1, len(screen_trail) - 1)
            )
            strength = old_strength + (1.0 - old_strength) * 0.5
            trail_colour = (
                colour[0] * strength,
                colour[1] * strength,
                colour[2] * strength,
            )
            ctx.rgb(*trail_colour)
            ctx.line_width = 1.4
            ctx.begin_path()
            ctx.move_to(*screen_trail[index - 1])
            ctx.line_to(*screen_trail[index])
            ctx.stroke()
            ctx.arc(
                screen_trail[index - 1][0],
                screen_trail[index - 1][1],
                1.15,
                0,
                2 * math.pi,
                True,
            ).fill()
        ctx.line_width = 1

        display_heading = self._display_heading()
        speed = item.get("speed", 0.0) or 0.0
        vector_len = 6.0 + min(float(speed), 600.0) / 600.0 * 12.0
        vdx, vdy = heading_vector(
            relative_bearing(item.get("track", 0.0), display_heading), vector_len
        )
        ctx.rgb(*colour)
        ctx.line_width = 1.5
        ctx.begin_path()
        ctx.move_to(x, y)
        ctx.line_to(x + vdx, y + vdy)
        ctx.stroke()
        ctx.line_width = 1

        self._draw_aircraft_symbol(ctx, x, y, item, colour, display_heading)

        if item.get("attention"):
            # A fine halo makes unusual traffic visible without adding another
            # tiny word to the already busy radar display.
            ctx.rgb(*colour)
            ctx.line_width = 1.1
            ctx.arc(x, y, 9.5, 0, 2 * math.pi, True).stroke()
            ctx.line_width = 1

        if item is self.selected_item:
            ctx.rgb(*YELLOW)
            ctx.line_width = 1.5
            ctx.arc(x, y, 8, 0, 2 * math.pi, True).stroke()
            ctx.line_width = 1

        return x, y, colour

    def _draw_aircraft_labels(self, ctx, aircraft_points):
        """Place large callsigns around aircraft with minimal overlap."""
        if getattr(self, "following", False):
            return
        occupied = []
        ctx.font_size = AIRCRAFT_LABEL_SIZE
        show_both = len(aircraft_points) == 1
        show_routes = int(self.label_elapsed / 3000) % 2 == 1
        for item, x, y, colour in aircraft_points:
            callsign = item.get("callsign", "")
            route = self.route_cache.get(callsign, "")
            if not callsign:
                continue
            lines = [callsign]
            if route and show_both:
                lines.append(route)
            elif route and show_routes:
                lines[0] = route
            widths = [ctx.text_width(line) for line in lines]
            width = max(widths)
            line_extra = 14 * (len(lines) - 1)
            candidates = (
                (x + 10, y - 3),
                (x - width - 10, y - 3),
                (x - width / 2, y - 13),
                (x - width / 2, y + 16),
                (x + 10, y + 14),
                (x - width - 10, y + 14),
            )
            chosen = candidates[0]
            for tx, ty in candidates:
                box = (
                    tx - 2,
                    ty - AIRCRAFT_LABEL_SIZE + 3,
                    tx + width + 2,
                    ty + 3 + line_extra,
                )
                if max(abs(box[0]), abs(box[2])) > 104 or max(abs(box[1]), abs(box[3])) > 104:
                    continue
                if any(
                    box[0] < old[2] and box[2] > old[0]
                    and box[1] < old[3] and box[3] > old[1]
                    for old in occupied
                ):
                    continue
                chosen = (tx, ty)
                break
            tx, ty = chosen
            box = (
                tx - 2,
                ty - AIRCRAFT_LABEL_SIZE + 3,
                tx + width + 2,
                ty + 3 + line_extra,
            )
            occupied.append(box)

            link_x = min(max(x, box[0]), box[2])
            link_y = min(max(y, box[1]), box[3])
            ctx.rgb(*colour).begin_path()
            ctx.move_to(x, y).line_to(link_x, link_y).stroke()
            ctx.rgba(0, 0, 0, 0.82).rectangle(
                box[0], box[1], box[2] - box[0], box[3] - box[1]
            ).fill()
            ctx.rgb(*colour).rectangle(
                box[0], box[1], box[2] - box[0], box[3] - box[1]
            ).stroke()
            ctx.rgb(*colour)
            for line_index, line in enumerate(lines):
                line_x = tx + (width - widths[line_index]) / 2
                ctx.move_to(line_x, ty + line_index * 14).text(line)

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
        ctx.move_to(-ctx.text_width(title) / 2, -77).text(title)
        ctx.font_size = 10
        subtitle = "LIVE ADS-B / TILDAGON"
        ctx.rgb(*GPS_TEXT).move_to(-ctx.text_width(subtitle) / 2, -55).text(subtitle)

        ctx.font_size = 14
        text = "Scanning the skies..."
        ctx.rgb(*YELLOW).move_to(-ctx.text_width(text) / 2, 13).text(text)
        ctx.font_size = 9
        prompt = "PRESS B FOR DEMO"
        ctx.rgb(*GPS_TEXT).move_to(-ctx.text_width(prompt) / 2, 70).text(prompt)
        prompt = "PRESS C FOR MANUAL"
        ctx.rgb(*WHITE).move_to(-ctx.text_width(prompt) / 2, 85).text(prompt)

    def _demo_aircraft_xy(self, stage, progress):
        if stage.get("emergency"):
            entry = min(1.0, progress / 0.28)
            return -58.0 + entry * 58.0, -8.0 + entry * 8.0
        return (
            -58.0 + progress * 116.0,
            -8.0 + math.sin(progress * 2 * math.pi) * 8.0,
        )

    def _draw_traffic_demo(self, ctx):
        """Animate a round-safe, self-explaining special-traffic showcase."""
        stage = DEMO_STAGES[self.demo_stage]
        colour = stage["colour"]
        self._draw_grid(ctx)

        sweep = (self.demo_elapsed % 1800) * 360.0 / 1800.0
        sx, sy = heading_vector(sweep, 71)
        ctx.rgb(colour[0] * 0.45, colour[1] * 0.45, colour[2] * 0.45)
        ctx.line_width = 1.5
        ctx.begin_path().move_to(0, 0).line_to(sx, sy).stroke()
        ctx.line_width = 1

        progress = min(1.0, self.demo_elapsed / float(DEMO_STAGE_MS))
        if stage.get("emergency"):
            background_colour = (
                GRID_DIM[0] * 0.35,
                GRID_DIM[1] * 0.35,
                GRID_DIM[2] * 0.35,
            )
            for bx, by in ((-44, -31), (47, -25), (42, 28)):
                self._draw_aircraft_symbol(
                    ctx,
                    bx,
                    by,
                    DEMO_BACKGROUND_ITEM,
                    background_colour,
                    0,
                )

        x, y = self._demo_aircraft_xy(stage, progress)
        for trail_index in range(6, 0, -1):
            old_progress = max(0.0, progress - trail_index * 0.045)
            tx, ty = self._demo_aircraft_xy(stage, old_progress)
            strength = 0.12 + (6 - trail_index) * 0.075
            ctx.rgb(
                colour[0] * strength,
                colour[1] * strength,
                colour[2] * strength,
            )
            ctx.arc(tx, ty, 1.15, 0, 2 * math.pi, True).fill()

        ctx.rgb(*colour)
        ctx.line_width = 1.4
        ctx.begin_path().move_to(x, y).line_to(x + 17, y).stroke()
        ctx.line_width = 1
        self._draw_aircraft_symbol(ctx, x, y, stage, colour, 0)
        ctx.rgb(*colour)
        ctx.line_width = 1.1
        ctx.arc(x, y, 9.5, 0, 2 * math.pi, True).stroke()
        ctx.line_width = 1
        self._draw_aircraft_labels(ctx, [(stage, x, y, colour)])

        ctx.font_size = 12 if not stage.get("emergency") else 10
        title = "SIMULATED EMERGENCY" if stage.get("emergency") else "TRAFFIC GUIDE"
        ctx.rgb(*WHITE).move_to(-ctx.text_width(title) / 2, -91).text(title)
        ctx.font_size = 7
        hint = "B NEXT   E PREV   C/F EXIT"
        ctx.rgb(*ALT_TEXT).move_to(-ctx.text_width(hint) / 2, -73).text(hint)
        for index in range(len(DEMO_STAGES)):
            dot_colour = colour if index == self.demo_stage else GRID_DIM
            ctx.rgb(*dot_colour).arc(
                (index - 1.5) * 11, -58, 2.2, 0, 2 * math.pi, True
            ).fill()

        entry = min(400, self.demo_elapsed)
        card_top = 43 + int((400 - entry) * 18 / 400)
        ctx.rgba(0, 0, 0, 0.9).rectangle(-72, card_top, 144, 43).fill()
        ctx.font_size = 11
        ctx.rgb(*colour)
        ctx.move_to(-ctx.text_width(stage["title"]) / 2, card_top + 13).text(
            stage["title"]
        )
        ctx.font_size = 8
        ctx.rgb(*WHITE)
        ctx.move_to(-ctx.text_width(stage["line1"]) / 2, card_top + 27).text(
            stage["line1"]
        )
        ctx.rgb(*ALT_TEXT)
        ctx.move_to(-ctx.text_width(stage["line2"]) / 2, card_top + 38).text(
            stage["line2"]
        )

    def _draw_instructions(self, ctx):
        ctx.rgb(*BACKGROUND).rectangle(-120, -120, 240, 240).fill()
        ctx.font_size = 12
        ctx.rgb(*WHITE)
        title = "PLANE RADAR HELP"
        ctx.move_to(-ctx.text_width(title) / 2, -88).text(title)
        ctx.font_size = 9
        text = "CONTROLS & SETUP"
        ctx.rgb(*GPS_TEXT).move_to(-ctx.text_width(text) / 2, -70).text(text)
        draw_qr(ctx, 0, 7, 3)
        ctx.font_size = 9
        hint = "PRESS C TO CLOSE"
        ctx.rgb(*YELLOW).move_to(-ctx.text_width(hint) / 2, 92).text(hint)

    def _draw_location_setup(self, ctx):
        ctx.rgb(*BACKGROUND).rectangle(-120, -120, 240, 240).fill()
        ctx.font_size = 20
        ctx.rgb(*WHITE)
        title = "RADAR OPTIONS"
        ctx.move_to(-ctx.text_width(title) / 2, -70).text(title)
        options = (
            "AUTO GPS / WI-FI",
            "UK POSTCODE",
            "COORDINATES",
            "BEARING: " + (
                ("{:03d} DEG".format(int(round(self.manual_bearing)) % 360))
                if self.manual_bearing is not None and self.heading_up
                else "NORTH-UP"
            ),
            "LED SWEEP: " + ("ON" if self.led_sweep else "OFF"),
            "LED LEVEL: {}%".format(self.led_sweep_brightness),
            "HEX FX: " + ("ON" if self.hexpansion_fx else "OFF"),
            "KEY LEVEL: {}%".format(self.hexpansion_brightness),
            "LOGO LEVEL: {}%".format(self.eeh_logo_brightness),
            "EEH LOGO: " + logo_port_label(self.eeh_logo_port),
            "TRAFFIC DEMO",
        )
        ctx.font_size = 17
        choice = options[self.location_choice]
        ctx.rgb(*GPS_TEXT).move_to(-ctx.text_width(choice) / 2, -18).text(choice)
        ctx.font_size = 11
        hint = "JOYSTICK / ARROWS"
        ctx.rgb(*ALT_TEXT).move_to(-ctx.text_width(hint) / 2, 30).text(hint)
        hint = "PRESS C TO SELECT"
        ctx.rgb(*YELLOW).move_to(-ctx.text_width(hint) / 2, 52).text(hint)
        ctx.font_size = 9
        hint = "BACK TO CANCEL"
        ctx.rgb(*ALT_TEXT).move_to(-ctx.text_width(hint) / 2, 83).text(hint)

    def _draw_location_warning(self, ctx):
        ctx.rgb(*BACKGROUND).rectangle(-120, -120, 240, 240).fill()
        ctx.rgb(*YELLOW).arc(0, 0, 102, 0, 2 * math.pi, True).stroke()
        ctx.font_size = 18
        ctx.rgb(*YELLOW)
        title = (
            "WI-FI INACCURATE"
            if self.location_warning_saved
            else "ROUGH LOCATION"
        )
        ctx.move_to(-ctx.text_width(title) / 2, -70).text(title)
        ctx.font_size = 13
        ctx.rgb(*WHITE)
        detail = "ABOUT {}km".format(int(round((self.wifi_accuracy or 0) / 1000.0)))
        ctx.move_to(-ctx.text_width(detail) / 2, -35).text(detail)
        if self.location_warning_saved:
            ctx.font_size = 10
            hint = "USING SAVED POSTCODE"
            ctx.rgb(*ALT_TEXT).move_to(-ctx.text_width(hint) / 2, 4).text(hint)
            ctx.font_size = 16
            choice = self.manual_postcode or "SAVED LOCATION"
            ctx.rgb(*GPS_TEXT).move_to(-ctx.text_width(choice) / 2, 34).text(choice)
        else:
            ctx.font_size = 11
            hint = "LEFT (E) / RIGHT (B)"
            ctx.rgb(*ALT_TEXT).move_to(-ctx.text_width(hint) / 2, 4).text(hint)
            ctx.font_size = 16
            choice = "CONTINUE" if self.location_warning_choice == 0 else "MANUAL"
            ctx.rgb(*GPS_TEXT).move_to(-ctx.text_width(choice) / 2, 34).text(choice)
        ctx.font_size = 10
        hint = "PRESS C TO SELECT"
        ctx.rgb(*WHITE).move_to(-ctx.text_width(hint) / 2, 65).text(hint)

    def _draw_location_notice(self, ctx):
        ctx.rgb(*BACKGROUND).rectangle(-120, -120, 240, 240).fill()
        ctx.rgb(*GRID).arc(0, 0, 82, 0, 2 * math.pi, True).stroke()
        ctx.font_size = 18
        ctx.rgb(*WHITE)
        title = self.location_notice or "LOCATION"
        ctx.move_to(-ctx.text_width(title) / 2, -19).text(title)
        ctx.font_size = 13
        ctx.rgb(*GPS_TEXT)
        detail = self.location_notice_detail or ""
        ctx.move_to(-ctx.text_width(detail) / 2, 15).text(detail)
        ctx.font_size = 9
        hint = "PRESS C TO CONTINUE"
        ctx.rgb(*YELLOW).move_to(-ctx.text_width(hint) / 2, 66).text(hint)

    def _draw_no_location(self, ctx):
        """Use the whole round-safe area while the radar cannot run."""
        ctx.rgb(*BACKGROUND).rectangle(-120, -120, 240, 240).fill()
        ctx.rgb(*GRID_DIM).arc(0, 0, 105, 0, 2 * math.pi, True).stroke()
        ctx.font_size = 19
        ctx.rgb(*YELLOW)
        title = "NO LOCATION"
        ctx.move_to(-ctx.text_width(title) / 2, -70).text(title)
        ctx.font_size = 13
        ctx.rgb(*WHITE)
        line = "RADAR IS PAUSED"
        ctx.move_to(-ctx.text_width(line) / 2, -34).text(line)
        ctx.font_size = 12
        ctx.rgb(*GPS_TEXT)
        line = "PRESS C / ENTER"
        ctx.move_to(-ctx.text_width(line) / 2, 8).text(line)
        line = "TYPE POSTCODE"
        ctx.move_to(-ctx.text_width(line) / 2, 32).text(line)
        ctx.font_size = 10
        ctx.rgb(*ALT_TEXT)
        line = "DOWN: RETRY AUTO"
        ctx.move_to(-ctx.text_width(line) / 2, 63).text(line)

    def _status_lines(self, ctx, text, max_width=140):
        words = str(text).split()
        lines = []
        current = ""
        for word in words:
            candidate = word if not current else current + " " + word
            if (
                not lines
                and current
                and ctx.text_width(candidate) > max_width
            ):
                lines.append(current)
                current = word
            else:
                current = candidate
        if current and len(lines) < 2:
            lines.append(current)
        if len(lines) == 2:
            while ctx.text_width(lines[1]) > max_width and len(lines[1]) > 3:
                lines[1] = lines[1][:-4].rstrip() + "..."
        return lines

    def _draw_status_card(self, ctx):
        ctx.font_size = 11
        lines = self._status_lines(ctx, self.status)
        height = 21 if len(lines) == 1 else 35
        # Keep the card inside the useful circular area of the physical LCD.
        top = 79 - height
        ctx.rgba(0, 0, 0, 0.86).rectangle(-78, top, 156, height).fill()
        ctx.rgb(*YELLOW)
        start_y = top + (14 if len(lines) == 1 else 13)
        for index, line in enumerate(lines):
            ctx.move_to(-ctx.text_width(line) / 2, start_y + index * 14).text(line)

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
        if self.view == "traffic_demo":
            self._draw_traffic_demo(ctx)
            ctx.restore()
            return
        if self.view == "location_setup":
            self._draw_location_setup(ctx)
            ctx.restore()
            return

        if self.location_warning:
            self._draw_location_warning(ctx)
            ctx.restore()
            return

        if self.location_notice is not None:
            self._draw_location_notice(ctx)
            ctx.restore()
            return

        if self.center_lat is None or self.center_lon is None:
            self._draw_no_location(ctx)
            ctx.restore()
            return

        self._draw_grid(ctx)
        self._draw_idle_sweep(ctx)
        if self.center_lat is not None and self.center_lon is not None:
            aircraft_points = []
            for item in self.aircraft:
                point = self._draw_aircraft(ctx, item)
                if point is not None:
                    aircraft_points.append((item, point[0], point[1], point[2]))
            self._draw_aircraft_labels(ctx, aircraft_points)
        self._draw_location_source(ctx)
        self._draw_selection(ctx)
        if self.status and self.location_notice is None:
            self._draw_status_card(ctx)
        ctx.restore()
        if self.dialog is not None:
            self.dialog.draw(ctx)


__app_export__ = PlaneRadarApp
