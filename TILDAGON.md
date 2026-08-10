# Plane Radar for Tildagon

This fork adds a native Tildagon/MicroPython version of Plane Radar while leaving the original ESP32-C3/Arduino firmware and upstream history intact.

Plane Radar shows live nearby aircraft from adsb.fi on the badge's round display, with a radar-style LED ring. It works on the original 2024 Tildagon and automatically unlocks extra controls when compatible GPS, Keepdexpansion and 2026 Spaceagon hardware are present.

## First start

The first launch opens with an animated radar boot screen and an on-badge QR code. Scan it to return to these instructions, or press **C** while the splash is visible for a larger QR help screen.

The first-run splash remains visible for a few seconds so there is time to scan it. Later launches use a shorter animated splash.

## Location

Plane Radar resolves its centre in this order: **GPS, Wi-Fi estimate, saved manual location**. It first checks Tildagon's optional Position capability, so a compatible GPS hexpansion can supply the radar centre without any app-specific configuration.

For compatibility with older GPS EEPROM firmware, Plane Radar also checks active hexpansion apps for a valid `position` property even when they do not advertise the newer capability.

If GPS has no fix, Plane Radar checks the existing MicroPython station first and uses Tildagon's normal top-level `wifi` manager only when necessary, then asks the public BeaconDB service for an approximate position. ESP-NOW firmware can reject explicit connect or scan operations with `Wifi Internal State Error`; these errors are logged but no longer abort the lookup. Plane Radar continues with BeaconDB's coarser IP-based estimate when scanning is unavailable. BeaconDB requires no API key. Wi-Fi requests can include nearby access-point identifiers and signal strengths; they are not made continuously. Estimates broader than 50 km, malformed responses, timeouts and service errors are ignored. A failure never erases or replaces the saved manual location.

The chosen location remains fixed while the local radar runs. Press **Down** whenever you want to retry the GPS → Wi-Fi sequence. If neither produces a usable result, the existing radar centre is retained.

Startup and manual refresh results temporarily take over the display in large text. Wi-Fi estimates broader than 5 km pause on a full-screen warning so you can continue with the rough centre or choose manual setup. Other results close automatically after a few seconds, or immediately with C, revealing the populated radar underneath. Large interaction screens label the physical C button explicitly and show a red pointer towards it.

Ongoing radar status is shown in a high-contrast, one- or two-line card at the bottom rather than the original tiny status text.

When no location is available, the empty radar is replaced by a full-screen, round-safe recovery page. C or keyboard Enter goes directly to postcode entry, typing a postcode character opens the same field with that character preserved, and Down retries automatic positioning. The automatic/manual chooser remains available after a location has been established.

Press **C/Confirm** to open the large-text radar options. Select **Auto GPS / Wi-Fi**, **UK Postcode**, **Coordinates**, or **LED Sweep: On/Off** with Left/Right and press C. UK postcodes are looked up through Postcodes.io (no API key required); spaces and letter case are optional. Decimal latitude/longitude entry remains available and saved manual locations remain available when automatic positioning fails.

## Standard controls

These controls work on both 2024 Tildagon and 2026 Spaceagon. The Spaceagon joystick direction inputs map to the same standard controls.

| Control | Action |
|---|---|
| Right | Cycle 2 / 5 / 10 / 15 km range |
| Left | Refresh aircraft immediately |
| Up | Toggle kilometres / miles |
| Down | Retry GPS, then Wi-Fi positioning |
| C / Confirm | Open radar options |
| Left + Right | Open Follow Flight without a keyboard |
| Cancel / Back | Minimise Plane Radar |

## Follow Flight

Plane Radar can leave your local position and follow a particular aircraft anywhere that live ADS-B position data is available.

### Keepdexpansion input

The Keepdexpansion is optional. If it is fitted and its keyboard app is running, **simply start typing a flight number or ADS-B callsign while the radar is visible**. Plane Radar opens the flight-search dialog and keeps the first character you typed. Pressing **Enter** with no preceding character opens an empty flight-search dialog.

Without a Keepdexpansion, press **Left + Right together** and enter the same value with Tildagon's normal text dialog.

Passenger-facing flight numbers and operational ADS-B callsigns are not always identical. Plane Radar performs a small best-effort conversion for several common UK airline prefixes (for example `BA123` to `BAW123`, `U2123` to `EZY123` and `FR123` to `RYR123`). If that does not find the aircraft, enter the operational callsign shown by an ADS-B tracker.

### Following behaviour

Once a target is found, Plane Radar locks onto its Mode-S hex identity and:

- moves the radar centre to the followed aircraft;
- keeps that aircraft fixed at the centre with a cyan direction marker;
- fetches and displays other aircraft around it using the normal range presets;
- updates the followed aircraft independently from the surrounding traffic;
- alternates automatically every **5 seconds** between the radar and a flight-data page.

The data page shows the information available from the live ADS-B feed, including callsign, aircraft type/registration when present, altitude, groundspeed, track, vertical rate, squawk and Mode-S hex.

While following:

| Control | Action |
|---|---|
| Left or Down | Refresh the followed aircraft now |
| Right | Change the surrounding-aircraft range |
| Up | Toggle km / miles |
| OK / Confirm | Follow a different flight |
| Cancel / Back | Stop following and restore your previous local radar position |

### Flight plan and progress bar

When route metadata can be resolved, the flight-data page shows the origin and destination plus a small journey progress bar and approximate distance remaining.

The percentage is deliberately labelled as an **estimate**. It is calculated from the aircraft's current great-circle distance to the destination compared with the origin-to-destination great-circle distance. It is not an airline operational flight-plan completion value, and it will not account for actual routing, holds, diversions or intermediate waypoints.

If route metadata is unavailable, the bar becomes an indeterminate moving marker. If the returned route is marked implausible for the aircraft's current position, Plane Radar shows the route as unverified rather than displaying a misleading percentage.

## RGB LED radar

While Plane Radar is foregrounded it temporarily takes control of Tildagon's 12 onboard RGB LEDs.

In normal/local radar mode:

- an optional green sweep rotates clockwise around the badge (toggle it from Radar Options);
- aircraft illuminate the LED sector matching their bearing on the radar;
- closer in-range aircraft appear brighter red/magenta;
- off-scale aircraft remain visible as dim magenta bearing cues;
- a subtle blue marker across the top LED pair indicates a GPS-derived radar centre.

In **Follow Flight** radar view the normal sweep and nearby traffic remain, with two extra directional cues:

- **cyan** points in the followed aircraft's current direction of travel;
- **green** points towards the resolved destination when route data is available.

If the followed aircraft temporarily disappears from the live feed, the ring gains a **red pulse** while Plane Radar tries to reacquire it.

On the alternating flight-data page the 12 badge LEDs become a journey-progress ring: completed sectors are teal/green, the current sector is brighter cyan and remaining sectors are dim blue. When route progress is unknown they use an indeterminate cyan state instead.

When Plane Radar is minimised or terminated it restores the normal Tildagon LED pattern.

## Keepdexpansion RGB backlight

The Keepdexpansion's RGB backlight is used as a second, quieter status display while a flight is being followed:

- with verified route progress, the logical keyboard light segments fill from teal/green towards cyan as the journey advances;
- with a target lock but no usable route percentage, the keyboard gives a cyan heartbeat;
- if the ADS-B target is lost, the keyboard pulses red.

Plane Radar only borrows the keyboard LEDs when their driver reports them available. It releases ownership when following stops, when the app is minimised, or when it terminates. If the keyboard previously had a static custom colour, Plane Radar restores that colour; if it was following the normal Tildagon pattern, the driver resumes doing so.

## Spaceagon enhancements

Spaceagon support is optional and detected at runtime. Installing Plane Radar never requires the 2026 frontboard, and the base radar remains compatible with a 2024 Tildagon.

### Touch the sky

The twelve Spaceagon touch sensors are treated like a clock face. Touch the part of the badge corresponding to an aircraft's direction and Plane Radar selects the nearest aircraft in that sector.

For example:

- **Touch 12** inspects traffic near the top of the display;
- **Touch 3** inspects traffic to the right;
- **Touch 6** inspects traffic below;
- **Touch 9** inspects traffic to the left.

A selected aircraft is highlighted and a temporary detail card shows its callsign/type, altitude, distance and groundspeed.

When heading-up mode is active the touch sectors rotate with the radar, so you still touch the physical direction in which the aircraft appears.

### Proximity zoom

The two side proximity sensors become hands-free range controls:

- **Left proximity** decreases the range (zooms in);
- **Right proximity** increases the range (zooms out).

Range is clamped at the 5 km and 25 km presets rather than wrapping around.

### Heading-up compass mode

Spaceagon's magnetometer can rotate the radar so the top of the screen represents the direction the badge is pointing. Aircraft positions, cardinal labels, aircraft nose headings, track vectors and the RGB traffic LEDs all rotate together.

**Joystick Fire** toggles between normal north-up and heading-up mode.

Before using heading-up for the first time, calibrate the zero direction:

1. Use a known compass and point the **top of the Spaceagon north**.
2. Press and hold **Joystick Fire** for at least about 1.2 seconds.
3. Plane Radar stores that magnetometer reading as north and enables heading-up mode.

A short Fire press then toggles heading-up on/off while preserving the calibration.

> Compass support is deliberately marked experimental until it has been checked on physical Spaceagon hardware. The current implementation uses the raw horizontal magnetometer axes plus the saved north offset; we may need to adjust axis direction or add fuller hard-iron calibration after real-badge testing.

## Display behaviour

The default radar remains north-up. It preserves the upstream project's 5/10/15/25 km ring presets, callsign and altitude labels, heading triangles, track/speed vectors and off-scale direction dots.

When Spaceagon heading-up is enabled, a cyan `HDG` marker and numeric heading appear on screen. `SP` indicates that Spaceagon-only controls are available. The local location marker shows `GPS`, `MAN` or `NO LOC`; while following a flight it changes to `FLT`.

The UI is drawn for the badge's native 240×240 display. Font sizes and labels are intentionally small and sparse rather than assuming a phone-like high-resolution display.

## Host-side tests

The geometry, ADS-B parsing, GPS validation, LED mapping, Spaceagon helpers and flight-follow route calculations can be tested without badge hardware:

```sh
python -m unittest discover -s tests -v
```

The app source can also be syntax checked with standard Python:

```sh
python -m py_compile app.py radar_base.py postcode.py wifi_location.py flight_app.py adsb.py flight_follow.py keebdeck.py radar_math.py location_provider.py led_radar.py spaceagon.py instructions_qr.py
```

## Publishing

`tildagon.toml` declares Wi-Fi plus optional Position-provider, RGB-hexpansion and 2026-frontboard enhancements. Before the first app-store release, add the repository topic `tildagon-app` and create a release/tag matching the metadata version (initially `v0.1.0`).

The original C++ firmware remains in this fork to preserve upstream history and attribution, while `.gitattributes` excludes the original development tree and host tests from Tildagon release archives.

## Current differences from the ESP32-C3 firmware

The Tildagon port does not yet include the embedded major-airport runway overlay or the original browser configuration portal. The portal is unnecessary because Tildagon already manages Wi-Fi and app settings. The runway overlay can be ported independently later.

Network requests currently use Tildagon's synchronous `requests` module, so a slow HTTPS request may briefly pause the UI during a poll.

## Data and attribution

Original Plane Radar project: **MatixYo/ESP32-Plane-Radar**, MIT licensed. This port retains the same licence and uses adsb.fi for live aircraft data. Follow Flight additionally uses adsb.lol/VRS standing route data when available to resolve origin and destination metadata.
