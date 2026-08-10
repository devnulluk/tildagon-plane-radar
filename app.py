"""Plane Radar public entry point with compatibility-preserving controls."""
from events.input import BUTTON_TYPES

try:
    from .flight_app import PlaneRadarApp as _FlightRadarApp
except ImportError:
    from flight_app import PlaneRadarApp as _FlightRadarApp


class PlaneRadarApp(_FlightRadarApp):
    """Keep base controls intact while exposing optional flight-follow mode."""

    def _intercept_controls(self):
        if self.view != "radar" or self.dialog is not None:
            return False

        # ENTER on a real keyboard is also a generic CONFIRM event. The
        # keyboard handler has already requested a flight dialog, so swallow
        # that alias rather than letting it open the manual-location dialog.
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
            return False

        # No keyboard? Press LEFT+RIGHT together to open Follow Flight. Single
        # LEFT/RIGHT presses retain their normal refresh/range behaviour.
        if (
            self.button_states.get(BUTTON_TYPES["LEFT"])
            and self.button_states.get(BUTTON_TYPES["RIGHT"])
        ):
            self.button_states.clear()
            self._open_flight_dialog()
            return True

        # In normal local-radar mode we deliberately do NOT consume OK, so the
        # original manual-location control remains available on every badge.
        return False


__app_export__ = PlaneRadarApp
