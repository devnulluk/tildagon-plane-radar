"""Plane Radar entry point with optional flight-follow and Keepdexpansion features."""

import random
import requests
import time
from app_components import TextDialog
from events.input import BUTTON_TYPES, ButtonDownEvent
from system.eventbus import eventbus
from tildagonos import tildagonos

try:
    from . import radar_base as base
    from .flight_follow import (
        build_route_url,
        build_target_url,
        initial_bearing,
        is_flight_key,
        nearest_target_within,
        normalise_flight_query,
        parse_route,
        parse_target,
        route_progress,
        route_remaining_km,
        should_end_emergency_follow,
    )
    from .keebdeck import KeebDeckLights
    from .adsb import build_squawk_url, needs_emergency_focus
    from .led_radar import red_chase_frame
except ImportError:
    import radar_base as base
    from flight_follow import (
        build_route_url,
        build_target_url,
        initial_bearing,
        is_flight_key,
        nearest_target_within,
        normalise_flight_query,
        parse_route,
        parse_target,
        route_progress,
        route_remaining_km,
        should_end_emergency_follow,
    )
    from keebdeck import KeebDeckLights
    from adsb import build_squawk_url, needs_emergency_focus
    from led_radar import red_chase_frame

FOLLOW_PAGE_MS = 5000
FOLLOW_TARGET_FIRST_MS = 2500
FOLLOW_TARGET_MS = 5000
FOLLOW_ROUTE_DELAY_MS = 1400
EMERGENCY_SCAN_MS = 30000
EMERGENCY_RADIUS_KM = 500


class PlaneRadarApp(base.PlaneRadarApp):
    """Base radar plus optional worldwide single-flight following."""

    def __init__(self):
        super().__init__()
        self.follow_target = None
        self.follow_query = None
        self.follow_route = None
        self.follow_progress = None
        self.follow_remaining_km = None
        self.follow_locked = False
        self.follow_lost_count = 0
        self.follow_home = None
        self.follow_page = "radar"
        self.follow_page_elapsed = 0
        self.follow_target_elapsed = 0
        self.follow_target_staggered = False
        self.follow_route_pending = False
        self.follow_route_elapsed = 0
        self.pending_follow_query = None
        self.pending_flight_open = False
        self.pending_flight_seed = ""
        self.pending_flight_cancel = False
        self.keyboard_confirm_pending = False
        self.pending_manual_open = False
        self.pending_location_submit = False
        self.pending_flight_submit = False
        self.pending_options_confirm = False
        self.pending_aircraft_list = False
        self.aircraft_list = []
        self.aircraft_list_choice = 0
        self.emergency_code = None
        self.emergency_simulated = False
        self.emergency_scan_elapsed = 0
        self.keeb_lights = KeebDeckLights(self)
        self._keyboard_handler = self._handle_keyboard_down
        eventbus.on(ButtonDownEvent, self._keyboard_handler, self)

    @property
    def following(self):
        return self.follow_target is not None

    def _handle_keyboard_down(self, event):
        """Typing on Keepdexpansion starts flight search from the radar."""
        try:
            key = event.button.find_parent_in_group("Keyboard")
        except Exception:
            key = None
        name = getattr(key, "name", "") if key is not None else ""
        if self.dialog is not None:
            if self.setup_stage is not None and name == "ENTER":
                self.pending_location_submit = True
                self.keyboard_confirm_pending = True
            elif self.setup_stage is None:
                if (
                    name == "ENTER"
                    or BUTTON_TYPES["CONFIRM"] in event.button
                ):
                    # TextDialog classifies Enter as a keyboard key before it
                    # reaches the generic CONFIRM branch. Submit explicitly.
                    self.pending_flight_submit = True
                    self.keyboard_confirm_pending = True
                elif name in ("ESC", "ESCAPE"):
                    self.pending_flight_cancel = True
            return
        if key is None:
            return
        if self.view == "location_setup" and name == "ENTER":
            self.pending_options_confirm = True
            return
        if self.view == "aircraft_list":
            return
        if self.view != "radar":
            return
        if self.center_lat is None or self.center_lon is None:
            if name == "ENTER" or is_flight_key(name):
                self.pending_manual_open = True
                self.pending_location_seed = "" if name == "ENTER" else name.upper()
                self.keyboard_confirm_pending = True
            return
        if name == "ENTER":
            # Let the keyboard's generic CONFIRM alias behave exactly like
            # physical C. Flight search still opens as soon as a callsign is
            # typed, without stealing Enter from Radar Options.
            return
        if name == "DOWN" and not self.following:
            self.pending_aircraft_list = True
            return
        if is_flight_key(name):
            self.pending_flight_open = True
            self.pending_flight_seed = name

    def _open_flight_dialog(self, seed=""):
        if self.dialog is not None:
            return
        self.dialog = TextDialog(
            "Flight / callsign",
            self,
            masked=False,
            on_complete=self._complete_flight_dialog,
            on_cancel=self._cancel_flight_dialog,
        )
        if seed:
            self.dialog.text = str(seed).upper()
        self.status = "Type flight / callsign"

    def _complete_flight_dialog(self):
        text = self.dialog.text if self.dialog is not None else ""
        self.dialog = None
        query = normalise_flight_query(text)
        if not query:
            self.status = "No flight entered"
            return
        if query == "7700":
            self._simulate_emergency()
            return
        self.pending_follow_query = query

    def _visible_aircraft(self):
        """Return selectable on-screen aircraft with useful identities."""
        visible = []
        for item in self.aircraft:
            callsign = item.get("callsign") or item.get("icao")
            point = self._screen_point_for_aircraft(item)
            if not callsign or point is None or point[2] > self.outer_km:
                continue
            visible.append(item)
        visible.sort(key=lambda item: str(item.get("callsign") or item.get("icao")))
        return visible

    def _open_aircraft_list(self):
        self.aircraft_list = self._visible_aircraft()
        self.aircraft_list_choice = 0
        self.button_states.clear()
        if not self.aircraft_list:
            self.status = "No visible flights"
            return
        self.view = "aircraft_list"

    def _handle_aircraft_list_input(self):
        if not self.aircraft_list:
            self.view = "radar"
            return
        if self.button_states.get(BUTTON_TYPES["UP"]):
            self.aircraft_list_choice = (
                self.aircraft_list_choice - 1
            ) % len(self.aircraft_list)
            self.button_states.clear()
        elif self.button_states.get(BUTTON_TYPES["DOWN"]):
            self.aircraft_list_choice = (
                self.aircraft_list_choice + 1
            ) % len(self.aircraft_list)
            self.button_states.clear()
        elif self.button_states.get(BUTTON_TYPES["CONFIRM"]):
            item = self.aircraft_list[self.aircraft_list_choice]
            query = item.get("callsign") or item.get("icao")
            self.button_states.clear()
            self.view = "radar"
            self._start_follow(query)
        elif self.button_states.get(BUTTON_TYPES["CANCEL"]):
            self.button_states.clear()
            self.view = "radar"

    def _cancel_flight_dialog(self):
        self._dialog_cleanup()
        self.status = "Flight search cancelled"

    def _get_json(self, url):
        response = None
        try:
            import wifi

            if not wifi.status():
                self.status = "Connecting Wi-Fi..."
                wifi.connect()
                if not wifi.wait():
                    self.status = "Wi-Fi unavailable"
                    return None
            response = requests.get(url)
            status_code = getattr(response, "status_code", 200)
            if status_code != 200:
                print("plane-radar: HTTP", status_code, url)
                return None
            return response.json()
        except Exception as exc:
            print("plane-radar: request failed:", exc)
            return None
        finally:
            if response is not None:
                try:
                    response.close()
                except Exception:
                    pass

    def _begin_follow_target(self, target, query, emergency_code=None, simulated=False):
        if self.follow_home is None:
            self.follow_home = (
                self.center_lat,
                self.center_lon,
                self.location_source,
                self.location_provider,
            )

        self.follow_query = target.get("callsign") or query
        self.follow_target = target
        self.follow_route = None
        self.follow_progress = None
        self.follow_remaining_km = None
        self.follow_locked = True
        self.follow_lost_count = 0
        self.follow_page = "radar"
        self.follow_page_elapsed = 0
        self.follow_target_elapsed = 0
        self.follow_target_staggered = False
        self.follow_route_pending = True
        self.follow_route_elapsed = 0
        self.center_lat = target["lat"]
        self.center_lon = target["lon"]
        self.location_source = "flight"
        self.location_provider = target.get("hex")
        self.poll_elapsed = 0
        self.aircraft = []
        self.selected_item = None
        self.emergency_code = emergency_code
        self.emergency_simulated = bool(simulated)
        self.keeb_lights.acquire()
        if emergency_code:
            self.status = "EMERGENCY " + emergency_code
        else:
            self.keeb_lights.paint(progress=None, locked=True, pulse=True)
            self.status = "Following " + self.follow_query
        return True

    def _start_follow(self, query):
        query = normalise_flight_query(query)
        if not query:
            return False
        self.status = "Finding " + query + "..."
        payload = self._get_json(build_target_url(callsign=query))
        target = parse_target(payload)
        if target is None:
            self.status = "Flight not found: " + query
            return False
        return self._begin_follow_target(target, query)

    def _target_from_radar_item(self, item, squawk=None):
        return {
            "hex": item.get("icao", ""),
            "callsign": item.get("callsign") or item.get("icao") or "?",
            "lat": item["lat"],
            "lon": item["lon"],
            "heading": item.get("heading", 0.0),
            "track": item.get("track", 0.0),
            "speed": item.get("speed", 0.0),
            "alt": item.get("alt", ""),
            "alt_ft": None,
            "type": item.get("type", ""),
            "model": item.get("model", "") or item.get("type", ""),
            "registration": "",
            "squawk": squawk or item.get("squawk", ""),
            "vertical_rate": None,
            "seen": 0.0,
        }

    def _simulate_emergency(self):
        candidates = [item for item in self.aircraft if item.get("lat") is not None]
        if not candidates:
            self.status = "No aircraft available for 7700 test"
            return False
        item = candidates[int(random.random() * len(candidates))]
        target = self._target_from_radar_item(item, "7700")
        return self._begin_follow_target(
            target, target["callsign"], emergency_code="7700", simulated=True
        )

    def _scan_global_emergency(self):
        self.emergency_scan_elapsed = 0
        payload = self._get_json(build_squawk_url("7700"))
        target = nearest_target_within(
            payload, self.center_lat, self.center_lon, EMERGENCY_RADIUS_KM
        )
        if target is None:
            return False
        return self._begin_follow_target(
            target, target.get("callsign") or "7700", emergency_code="7700"
        )

    def _stop_follow(self):
        if not self.following:
            return
        if self.follow_home is not None:
            (
                self.center_lat,
                self.center_lon,
                self.location_source,
                self.location_provider,
            ) = self.follow_home
        self.follow_home = None
        self.follow_target = None
        self.follow_query = None
        self.follow_route = None
        self.follow_progress = None
        self.follow_remaining_km = None
        self.follow_locked = False
        self.emergency_code = None
        self.emergency_simulated = False
        self.follow_route_pending = False
        self.follow_page = "radar"
        self.follow_page_elapsed = 0
        self.aircraft = []
        self.selected_item = None
        self.poll_elapsed = base.POLL_INTERVAL_MS
        self.keeb_lights.release()
        if self.center_lat is None or self.center_lon is None:
            self.status = "Stopped following - no local position"
        else:
            self.status = "Back to local radar"

    def _refresh_follow_target(self):
        if not self.following:
            return False
        hex_id = self.follow_target.get("hex")
        if self.follow_lost_count >= 2:
            hex_id = None
        payload = self._get_json(
            build_target_url(callsign=self.follow_query, hex_id=hex_id)
        )
        target = parse_target(payload, preferred_hex=hex_id)
        if target is None:
            self.follow_lost_count += 1
            self.follow_locked = False
            if should_end_emergency_follow(
                self.emergency_code,
                self.emergency_simulated,
                self.follow_lost_count,
            ):
                callsign = self.follow_query or "Emergency aircraft"
                self._stop_follow()
                self.status = callsign + " left emergency feed"
                return False
            self.status = "{} signal lost ({})".format(
                self.follow_query, self.follow_lost_count
            )
            return False

        self.follow_target = target
        self.follow_query = target.get("callsign") or self.follow_query
        self.follow_locked = True
        self.follow_lost_count = 0
        self.center_lat = target["lat"]
        self.center_lon = target["lon"]
        self.location_source = "flight"
        self.location_provider = target.get("hex")
        self._update_follow_progress()
        self.status = "Following " + self.follow_query
        return True

    def _fetch_follow_route(self):
        self.follow_route_pending = False
        if not self.following:
            return
        target = self.follow_target
        payload = self._get_json(
            build_route_url(self.follow_query, target["lat"], target["lon"])
        )
        self.follow_route = parse_route(payload)
        self._update_follow_progress()
        if self.follow_route is None:
            print("plane-radar: no route data for", self.follow_query)

    def _update_follow_progress(self):
        if not self.following or self.follow_route is None:
            self.follow_progress = None
            self.follow_remaining_km = None
            return
        target = self.follow_target
        self.follow_remaining_km = route_remaining_km(
            self.follow_route, target["lat"], target["lon"]
        )
        if self.follow_route.get("plausible", True):
            self.follow_progress = route_progress(
                self.follow_route, target["lat"], target["lon"]
            )
        else:
            self.follow_progress = None

    def _fetch_aircraft(self):
        if not self.following:
            super()._fetch_aircraft()
            for item in self.aircraft:
                squawk = item.get("squawk", "")
                if needs_emergency_focus(item):
                    target = self._target_from_radar_item(item, squawk)
                    self._begin_follow_target(
                        target,
                        target["callsign"],
                        emergency_code=squawk or "ADS-B",
                    )
                    break
            return
        super()._fetch_aircraft()
        target_callsign = (self.follow_query or "").upper()
        target_hex = str(self.follow_target.get("hex", "")).lower()
        self.aircraft = [
            item
            for item in self.aircraft
            if (
                str(item.get("callsign", "")).upper() != target_callsign
                and (
                    not target_hex
                    or str(item.get("icao", "")).lower() != target_hex
                )
            )
        ]
        if self.emergency_code:
            self.status = "EMERGENCY " + self.emergency_code
            return
        if self.follow_locked:
            self.status = "{}  ZOOM {}".format(
                self.follow_query, self._range_label()
            )
        else:
            self.status = self.follow_query + " signal lost"

    def _handle_follow_network(self, delta):
        if not self.following or self.dialog is not None:
            return
        self.follow_target_elapsed += delta
        target_due = (
            FOLLOW_TARGET_MS
            if self.follow_target_staggered
            else FOLLOW_TARGET_FIRST_MS
        )
        if self.follow_target_elapsed >= target_due:
            self.follow_target_elapsed = 0
            self.follow_target_staggered = True
            self._refresh_follow_target()

        if self.follow_route_pending:
            self.follow_route_elapsed += delta
            if self.follow_route_elapsed >= FOLLOW_ROUTE_DELAY_MS:
                self.follow_route_elapsed = 0
                self._fetch_follow_route()

        self.follow_page_elapsed += delta
        if self.follow_page_elapsed >= FOLLOW_PAGE_MS:
            self.follow_page_elapsed %= FOLLOW_PAGE_MS
            self.follow_page = "data" if self.follow_page == "radar" else "radar"

    def _intercept_controls(self):
        if self.view != "radar" or self.dialog is not None:
            return False

        if self.keyboard_confirm_pending:
            self.keyboard_confirm_pending = False
            self.button_states.clear()
            return False

        if self.following:
            if self.button_states.get(BUTTON_TYPES["CANCEL"]):
                self.button_states.clear()
                self._stop_follow()
                return True
            if self.button_states.get(BUTTON_TYPES["DOWN"]):
                self.button_states.clear()
                self._refresh_follow_target()
                self.follow_target_elapsed = 0
                self.follow_target_staggered = True
                self.poll_elapsed = 0
                return True
            if self.button_states.get(BUTTON_TYPES["LEFT"]):
                self.button_states.clear()
                self._refresh_follow_target()
                self.follow_target_elapsed = 0
                self.follow_target_staggered = True
                self.poll_elapsed = 0
                return True
            if (
                self.button_states.get(BUTTON_TYPES["CONFIRM"])
                and not self.suppress_confirm
            ):
                self.button_states.clear()
                self._open_flight_dialog()
                return True
        elif (
            self.center_lat is not None
            and self.center_lon is not None
            and self.button_states.get(BUTTON_TYPES["CONFIRM"])
            and not self.suppress_confirm
        ):
            self.button_states.clear()
            self._open_flight_dialog()
            return True
        return False

    def update(self, delta):
        if not self.following and self.view == "radar" and self.dialog is None:
            self.emergency_scan_elapsed += delta
            # Scan midway between local polls, avoiding back-to-back requests.
            if (
                self.emergency_scan_elapsed >= EMERGENCY_SCAN_MS
                and 1500 <= self.poll_elapsed <= 3500
            ):
                self._scan_global_emergency()

        if self.pending_flight_cancel or (
            self.dialog is not None
            and self.setup_stage is None
            and self.button_states.get(BUTTON_TYPES["CANCEL"])
        ):
            self.pending_flight_cancel = False
            self.button_states.clear()
            self._cancel_flight_dialog()

        if self.pending_location_submit:
            self.pending_location_submit = False
            self.keyboard_confirm_pending = False
            # TextDialog may already have consumed Enter. If it has not, make
            # the keyboard action submit the location field explicitly.
            if self.dialog is not None and self.setup_stage is not None:
                self._complete_location()
            self.button_states.clear()

        if self.pending_flight_submit:
            self.pending_flight_submit = False
            self.keyboard_confirm_pending = False
            if self.dialog is not None and self.setup_stage is None:
                self._complete_flight_dialog()
            self.button_states.clear()

        if self.pending_options_confirm:
            self.pending_options_confirm = False
            if self.view == "location_setup":
                self._select_location_option()

        if self.pending_aircraft_list:
            self.pending_aircraft_list = False
            if self.view == "radar" and self.dialog is None and not self.following:
                self._open_aircraft_list()

        if self.view == "aircraft_list":
            self._handle_aircraft_list_input()
            return

        if self.pending_manual_open and self.dialog is None:
            self.pending_manual_open = False
            self.pending_flight_open = False
            self.keyboard_confirm_pending = False
            self.location_notice = None
            self.location_notice_detail = None
            self.setup_stage = "postcode"
            self.button_states.clear()

        if self.pending_flight_open and self.dialog is None and self.view == "radar":
            seed = self.pending_flight_seed
            self.pending_flight_open = False
            self.pending_flight_seed = ""
            self.keyboard_confirm_pending = False
            self.button_states.clear()
            self._open_flight_dialog(seed)

        if self.pending_follow_query is not None and self.dialog is None:
            query = self.pending_follow_query
            self.pending_follow_query = None
            self._start_follow(query)

        self._intercept_controls()
        self._handle_follow_network(delta)
        super().update(delta)

    def _draw_location_source(self, ctx):
        if not self.following:
            return super()._draw_location_source(ctx)
        ctx.font_size = 7
        ctx.rgb(*base.CYAN).move_to(-105, -88).text("FLT")
        if self.spaceagon:
            ctx.rgb(*base.CYAN).move_to(77, -88).text("SP")
            if self.heading_up:
                ctx.rgb(*base.CYAN).move_to(76, -78).text("HDG")

    def _center_text(self, ctx, text, y, bold=False):
        """Draw centred text, with a subtle second pass for LCD legibility."""
        x = -ctx.text_width(text) / 2
        ctx.move_to(x, y).text(text)
        if bold:
            ctx.move_to(x + 0.55, y).text(text)
            ctx.move_to(x + 1.10, y).text(text)

    def _draw_follow_target_center(self, ctx):
        if not self.following:
            return
        target = self.follow_target
        display_heading = self._display_heading()
        if self.follow_route is not None:
            destination_bearing = initial_bearing(
                target["lat"],
                target["lon"],
                self.follow_route["destination_lat"],
                self.follow_route["destination_lon"],
            )
            path_direction = base.relative_bearing(
                destination_bearing, display_heading
            )
            pdx, pdy = base.heading_vector(path_direction, 39.0)
            ctx.rgb(*base.GRID)
            ctx.line_width = 1.1
            ctx.begin_path().move_to(0, 0).line_to(pdx, pdy).stroke()
            ctx.arc(pdx, pdy, 2.0, 0, 2 * base.math.pi, True).fill()
            ctx.line_width = 1
        direction = base.relative_bearing(
            target.get("track", target.get("heading", 0.0)), display_heading
        )
        fdx, fdy = base.heading_vector(direction, 7.0)
        rdx, rdy = -fdy * 0.55, fdx * 0.55
        bx, by = -fdx * 0.65, -fdy * 0.65
        colour = (
            base.RED
            if self.emergency_code or not self.follow_locked
            else base.CYAN
        )
        ctx.rgb(*colour)
        ctx.line_width = 1.2
        ctx.arc(0, 0, 9, 0, 2 * base.math.pi, True).stroke()
        ctx.begin_path()
        ctx.move_to(fdx, fdy)
        ctx.line_to(bx + rdx, by + rdy)
        ctx.line_to(bx - rdx, by - rdy)
        ctx.close_path()
        ctx.fill()
        ctx.line_width = 1

    def _draw_status_card(self, ctx):
        if not self.following:
            return super()._draw_status_card(ctx)
        target = self.follow_target
        route = self.follow_route
        callsign = self.follow_query or "?"
        path = ""
        if route is not None:
            path = "{}>{}".format(route["origin"], route["destination"])
        squawk = target.get("squawk") or "----"
        first = callsign + "  SQK" + squawk
        second = path or "PATH UNKNOWN"
        altitude = target.get("alt") or "ALT?"
        speed = int(round(float(target.get("speed", 0.0) or 0.0)))
        track = int(round(float(target.get("track", 0.0) or 0.0))) % 360
        third = "{}  {}KT  BRG{:03d}".format(altitude, speed, track)
        ctx.rgba(0, 0, 0, 0.90).rectangle(-84, 29, 168, 66).fill()
        ctx.font_size = 17
        while ctx.text_width(first) > 160 and ctx.font_size > 13:
            ctx.font_size -= 1
        ctx.rgb(*(base.RED if self.emergency_code else base.CYAN))
        self._center_text(ctx, first, 48, bold=True)
        ctx.font_size = 16
        ctx.rgb(*base.GPS_TEXT)
        self._center_text(ctx, second, 70, bold=True)
        ctx.font_size = 13
        ctx.rgb(*base.WHITE)
        self._center_text(ctx, third, 91, bold=True)

    def _draw_progress_bar(self, ctx, y, width=156, height=7):
        left = -width / 2
        ctx.rgb(*base.GRID_DIM).rectangle(left, y, width, height).stroke()
        if self.follow_progress is None:
            travel = int(self.follow_page_elapsed / 100) % max(1, int(width - 24))
            ctx.rgb(*base.CYAN).rectangle(
                left + travel, y + 1, 22, height - 2
            ).fill()
            return
        fill = max(1, int((width - 2) * self.follow_progress))
        ctx.rgb(*base.CYAN).rectangle(
            left + 1, y + 1, fill, height - 2
        ).fill()

    def _draw_follow_data(self, ctx):
        target = self.follow_target
        emergency = bool(self.emergency_code)
        ctx.rgb(*base.BACKGROUND).rectangle(-120, -120, 240, 240).fill()
        ctx.font_size = 14
        ctx.rgb(*(base.RED if emergency else base.CYAN))
        if emergency:
            prefix = "SIM " if self.emergency_simulated else ""
            header = prefix + "EMERGENCY " + self.emergency_code
        else:
            header = "FOLLOWING"
        self._center_text(ctx, header, -89, bold=True)

        ctx.font_size = 29
        ctx.rgb(*(base.WHITE if self.follow_locked else base.RED))
        callsign = self.follow_query or "?"
        while ctx.text_width(callsign) > 174 and ctx.font_size > 20:
            ctx.font_size -= 1
        self._center_text(ctx, callsign, -64, bold=True)

        route = self.follow_route
        ctx.font_size = 20
        ctx.rgb(*base.YELLOW)
        if route is not None:
            route_text = "{} > {}".format(route["origin"], route["destination"])
        elif emergency:
            route_text = "PATH UNKNOWN"
        else:
            route_text = "ROUTE UNKNOWN"
        while ctx.text_width(route_text) > 174 and ctx.font_size > 15:
            ctx.font_size -= 1
        self._center_text(ctx, route_text, -37, bold=True)

        ctx.font_size = 15
        ctx.rgb(*base.ALT_TEXT)
        identity = target.get("model") or target.get("type") or "MODEL UNKNOWN"
        if target.get("registration"):
            identity += "  " + target["registration"]
        while ctx.text_width(identity) > 174 and len(identity) > 5:
            identity = identity[:-4].rstrip() + "..."
        self._center_text(ctx, identity, -14, bold=True)

        alt_ft = target.get("alt_ft")
        alt_text = "?"
        if isinstance(alt_ft, (int, float)):
            alt_text = "{:,}ft".format(int(round(alt_ft)))
        elif target.get("alt"):
            alt_text = target["alt"]
        speed = int(round(float(target.get("speed", 0.0) or 0.0)))
        ctx.font_size = 17
        ctx.rgb(*base.WHITE)
        line = "ALT {}   GS {}kt".format(alt_text, speed)
        self._center_text(ctx, line, 9, bold=True)
        ctx.font_size = 14
        track = int(round(float(target.get("track", 0.0) or 0.0))) % 360
        vertical = target.get("vertical_rate")
        vtext = ""
        if isinstance(vertical, (int, float)):
            vtext = "  VS {:+d}".format(int(round(vertical)))
        line = "BRG {:03d}{}".format(track, vtext)
        ctx.rgb(*base.ALT_TEXT)
        self._center_text(ctx, line, 31, bold=True)

        ctx.font_size = 13
        squawk = target.get("squawk") or "----"
        ctx.rgb(*(base.RED if emergency else base.ALT_TEXT))
        self._center_text(ctx, "SQUAWK " + squawk, 51, bold=True)

        if self.follow_progress is not None:
            pct = int(round(self.follow_progress * 100.0))
            progress_text = "~{}% OF ROUTE".format(pct)
        elif route is not None and not route.get("plausible", True):
            progress_text = "ROUTE UNVERIFIED"
        else:
            progress_text = "FLIGHT PLAN UNKNOWN"

        if self.follow_remaining_km is not None and route is not None:
            remaining = self.follow_remaining_km
            if self.use_miles:
                remaining /= base.KM_PER_MILE
                progress_text = "~{}MI TO {}".format(
                    int(round(remaining)), route["destination"]
                )
            else:
                progress_text = "~{}KM TO {}".format(
                    int(round(remaining)), route["destination"]
                )
        ctx.rgb(*base.GPS_TEXT)
        self._center_text(ctx, progress_text, 70, bold=True)

        ctx.font_size = 13
        ctx.rgb(*base.YELLOW)
        self._center_text(ctx, "F: BACK TO RADAR", 94, bold=True)

    def _draw_aircraft_list(self, ctx):
        ctx.rgb(*base.BACKGROUND).rectangle(-120, -120, 240, 240).fill()
        ctx.font_size = 15
        ctx.rgb(*base.WHITE)
        self._center_text(ctx, "VISIBLE FLIGHTS", -91, bold=True)

        count = len(self.aircraft_list)
        start = max(0, min(self.aircraft_list_choice - 2, count - 5))
        shown = self.aircraft_list[start:start + 5]
        for row, item in enumerate(shown):
            index = start + row
            y = -61 + row * 30
            selected = index == self.aircraft_list_choice
            if selected:
                ctx.rgba(0.0, 0.36, 0.18, 0.78).rectangle(
                    -82, y - 12, 164, 28
                ).fill()
            callsign = str(item.get("callsign") or item.get("icao") or "?")
            route = self.route_cache.get(item.get("callsign", ""), "")
            ctx.font_size = 13 if selected else 11
            ctx.rgb(*(base.YELLOW if selected else base.WHITE))
            self._center_text(ctx, callsign, y, bold=selected)
            ctx.font_size = 9
            ctx.rgb(*(base.GPS_TEXT if route else base.ALT_TEXT))
            self._center_text(ctx, route or "ROUTE UNKNOWN", y + 12, bold=selected)

        ctx.font_size = 9
        ctx.rgb(*base.YELLOW)
        footer = "UP/DOWN  ENTER  F BACK"
        self._center_text(ctx, footer, 94, bold=True)

    def draw(self, ctx):
        if self.view == "aircraft_list":
            ctx.save()
            self._draw_aircraft_list(ctx)
            ctx.restore()
            return
        if (
            self.following
            and self.follow_page == "data"
            and self.view == "radar"
            and self.dialog is None
        ):
            ctx.save()
            self._draw_follow_data(ctx)
            ctx.restore()
            return

        super().draw(ctx)
        if self.following and self.view == "radar" and self.dialog is None:
            ctx.save()
            self._draw_follow_target_center(ctx)
            ctx.restore()

    def _progress_led_frame(self, count, pulse):
        if not self.follow_locked:
            level = 76 if pulse else 20
            return [(level, 0, 0) for _ in range(count)]
        if self.follow_progress is None:
            level = 32 if pulse else 12
            return [(0, level, level) for _ in range(count)]
        progress = max(0.0, min(1.0, self.follow_progress))
        scaled = progress * count
        frame = []
        for index in range(count):
            if index + 1 <= scaled:
                frame.append((0, 38, 24))
            elif index <= scaled < index + 1:
                frame.append((20, 120 if pulse else 82, 130 if pulse else 88))
            else:
                frame.append((0, 0, 7))
        return frame

    def _update_radar_leds(self):
        if not self.following:
            self.keeb_lights.release()
            return super()._update_radar_leds()

        if self.emergency_code:
            # A steady head-and-tail chase identifies an emergency without
            # flashing the whole badge or repeatedly plunging it into darkness.
            frame = red_chase_frame(12, time.ticks_ms())
            self.keeb_lights._write(frame)
            try:
                for led, colour in enumerate(frame, 1):
                    tildagonos.leds[led] = colour
                tildagonos.leds.write()
            except Exception as exc:
                print("plane-radar: emergency LED chase failed:", exc)
            return

        pulse = (self.sweep_led % 2) == 0
        self.keeb_lights.paint(
            progress=self.follow_progress,
            locked=self.follow_locked,
            pulse=pulse,
        )

        if self.follow_page == "data":
            frame = self._progress_led_frame(12, pulse)
            try:
                for led, colour in enumerate(frame, 1):
                    tildagonos.leds[led] = colour
                tildagonos.leds.write()
            except Exception as exc:
                print("plane-radar: follow LED update failed:", exc)
            self.sweep_led = self.sweep_led % 12 + 1
            return

        super()._update_radar_leds()
        try:
            frame = [tildagonos.leds[index] for index in range(1, 13)]
            target = self.follow_target
            display_heading = self._display_heading()

            track = base.relative_bearing(target.get("track", 0.0), display_heading)
            track_led = base.led_index_for_bearing(track)
            frame[track_led - 1] = base.max_rgb(
                frame[track_led - 1], (15, 115 if pulse else 80, 130)
            )

            if self.follow_route is not None:
                dest_bearing = initial_bearing(
                    target["lat"],
                    target["lon"],
                    self.follow_route["destination_lat"],
                    self.follow_route["destination_lon"],
                )
                dest_relative = base.relative_bearing(dest_bearing, display_heading)
                dest_led = base.led_index_for_bearing(dest_relative)
                frame[dest_led - 1] = base.max_rgb(
                    frame[dest_led - 1], (0, 70, 24)
                )

            if not self.follow_locked:
                for index in range(12):
                    frame[index] = base.max_rgb(
                        frame[index], (42 if pulse else 15, 0, 0)
                    )

            for led, colour in enumerate(frame, 1):
                tildagonos.leds[led] = colour
            tildagonos.leds.write()
        except Exception as exc:
            print("plane-radar: target LED overlay failed:", exc)

    def minimise(self):
        self.keeb_lights.release()
        super().minimise()

    def terminate(self, restore_pattern=False):
        self.keeb_lights.release()
        try:
            eventbus.remove(ButtonDownEvent, self._keyboard_handler, self)
        except Exception:
            pass
        super().terminate(restore_pattern=restore_pattern)


__app_export__ = PlaneRadarApp
