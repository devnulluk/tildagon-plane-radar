# Plane Radar for Tildagon

This fork adds a native Tildagon/MicroPython version of Plane Radar while leaving the original ESP32-C3/Arduino firmware and upstream history intact.

Plane Radar shows live nearby aircraft from adsb.fi on the badge's round display, with a radar-style LED ring. It works on the original 2024 Tildagon and automatically unlocks extra controls when compatible GPS, Keepdexpansion and 2026 Spaceagon hardware are present.

## First start

Plane Radar opens with an animated radar boot screen. Press **C** while the splash is visible to open the full QR manual screen.

The first-run splash remains visible for five seconds; later launches remain visible for three seconds. Press **C** for the QR manual or **B/Right** for the animated Traffic Guide. The guide loops through air ambulance, police, military and database-marked interesting traffic, then ends with a clearly simulated 7700 focus. Each chapter has a moving example, its display symbol, an explanatory card and the matching LED animation. B/Right and E/Left step through the guide; C or Back exits. It can also be reopened at any time from Radar Options.

## Location

Plane Radar resolves its centre in this order: **GPS, Wi-Fi estimate, saved manual location**. It first checks Tildagon's optional Position capability, so a compatible GPS hexpansion can supply the radar centre without any app-specific configuration.

For compatibility with older GPS EEPROM firmware, Plane Radar also checks active hexpansion apps for a valid `position` property even when they do not advertise the newer capability.

If GPS has no fix, Plane Radar checks the existing MicroPython station first and uses Tildagon's normal top-level `wifi` manager only when necessary, then asks the public BeaconDB service for an approximate position. ESP-NOW firmware can reject explicit connect or scan operations with `Wifi Internal State Error`; these errors are logged but no longer abort the lookup. Plane Radar continues with BeaconDB's coarser IP-based estimate when scanning is unavailable. BeaconDB requires no API key. Wi-Fi requests can include nearby access-point identifiers and signal strengths; they are not made continuously. Estimates broader than 50 km, malformed responses, timeouts and service errors are ignored. A failure never erases or replaces the saved manual location.

The chosen location remains fixed while the local radar runs. Press **Down** whenever you want to retry the GPS → Wi-Fi sequence. If neither produces a usable result, the existing radar centre is retained.

Startup and manual refresh results temporarily take over the display in large text. If a Wi-Fi estimate is broader than 5 km and a postcode has previously been saved, Plane Radar shows a warning and automatically keeps the saved postcode location. If no postcode is saved, the warning still offers the rough Wi-Fi centre or manual setup. Other results close automatically after a few seconds, or immediately with C, revealing the populated radar underneath. Large interaction screens label the physical controls explicitly.

Ongoing radar status is shown in a high-contrast, one- or two-line card at the bottom rather than the original tiny status text.

## Emergency focus

The local radar watches the ADS-B emergency status and the standard 7500,
7600 and 7700 squawks. It also checks adsb.fi's dedicated 7700 endpoint every
30 seconds and acts on the nearest result within 500 km, allowing
general-emergency aircraft to be detected across a broad UK-sized region
without downloading ordinary country-wide traffic. When detected,
Plane Radar switches into focused flight-following. The selected aircraft stays
at the centre, surrounding traffic remains dim and unlabeled, and the radar
alternates with a full details page. Two opposing red heads and their short
tails chase continuously around the LED ring, making 7700 visibly different
from the slower broad military sweep without flashing the whole ring. Press
Back to return to the local radar.

For demonstration and testing, type **7700** as a flight/callsign. Plane Radar
chooses one of the currently visible aircraft, clearly labels the alert as
simulated, and exercises the same focus screen and LED chase. This display is
for interest only and must not be treated as an authoritative emergency alert.

When no location is available, the empty radar is replaced by a full-screen, round-safe recovery page. C or keyboard Enter goes directly to postcode entry, typing a postcode character opens the same field with that character preserved, and Down retries automatic positioning. The automatic/manual chooser remains available after a location has been established.

Press **C/Confirm** to open the large-text radar options. Select **Auto GPS / Wi-Fi**, **UK Postcode**, **Coordinates**, **Bearing**, **LED Sweep: On/Off**, or **Traffic Demo** with the joystick, any keyboard arrow pair, or physical E/B, then press C. UK postcodes are looked up through Postcodes.io (no API key required); spaces and letter case are optional. After a successful lookup, the postcode is saved and prefilled next time. Submit postcode, coordinate and bearing fields with physical C or keyboard Enter. Decimal latitude/longitude entry remains available and saved manual locations remain available when automatic positioning fails.

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

The default range is 10 km. The 2 and 5 km presets provide close-up views, while 15 km shows more traffic near the visible horizon.

## Follow Flight

Plane Radar can leave your local position and follow a particular aircraft anywhere that live ADS-B position data is available.

### Keepdexpansion input

The Keepdexpansion is optional. If it is fitted and its keyboard app is running, **simply start typing a flight number or ADS-B callsign while the radar is visible**. Plane Radar opens the flight-search dialog and keeps the first character you typed. Enter remains equivalent to physical C for menus and location setup. Press Escape or physical F to close flight search.

Without a Keepdexpansion, press **Left + Right together** and enter the same value with Tildagon's normal text dialog.

Passenger-facing flight numbers and operational ADS-B callsigns are not always identical. Plane Radar performs a small best-effort conversion for several common UK airline prefixes (for example `BA123` to `BAW123`, `U2123` to `EZY123` and `FR123` to `RYR123`). If that does not find the aircraft, enter the operational callsign shown by an ADS-B tracker.

### Following behaviour

Once a target is found, Plane Radar locks onto its Mode-S hex identity and:

- moves the radar centre to the followed aircraft;
- keeps that aircraft fixed at the centre with a cyan direction marker, or red during an emergency focus;
- fetches and displays other aircraft as dim, unlabeled background context using the normal range presets;
- draws a destination-path ray when a route can be resolved;
- updates the followed aircraft independently from the surrounding traffic;
- alternates automatically every **5 seconds** between the radar and a flight-data page.

The focused radar card shows callsign, route, altitude, groundspeed, bearing/track and squawk. The alternating data page adds the aircraft model/registration, vertical rate, Mode-S hex, route progress and distance remaining when those fields are available from the live feeds.

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

Aircraft carrying readsb's database **interesting** flag receive a fine amber halo. Plane Radar also recognises deliberately narrow public metadata for three useful UK categories. When an air-ambulance, police or military aircraft is inside the selected radar range, the LEDs at its bearing breathe smoothly without switching fully off: **green** for a recognised air ambulance, **blue** for police, and **red** for military traffic. The on-screen aircraft and halo use the same colour. If several different special categories are in range together, the ring switches to a full sweep of each present colour in turn rather than displaying competing alerts simultaneously.

Classification is best-effort: air ambulance and police identification relies on published emergency status, callsign and a small set of strong registration patterns; military and generic-interest status use readsb database flags. Public ADS-B metadata is incomplete, so an aircraft may be absent or ordinarily coloured. This is not an operational emergency-services alert.

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

A selected aircraft is highlighted and a temporary detail card shows its callsign/type, altitude, distance and groundspeed. Radar labels alternate between the callsign and resolved origin-destination code (for example `BAW88C` and `YVR-LHR`). When only one aircraft is inside the radar range, its expanded label shows both lines together. Route lookups are progressive and cached only for the current app session.

When heading-up mode is active the touch sectors rotate with the radar, so you still touch the physical direction in which the aircraft appears.

### Proximity zoom

The two side proximity sensors become hands-free range controls:

- **Left proximity** decreases the range (zooms in);
- **Right proximity** increases the range (zooms out).

Range is clamped at the 2 km and 15 km presets rather than wrapping around.

### Heading-up compass mode

Spaceagon's magnetometer can rotate the radar so the top of the screen represents the direction the badge is pointing. Aircraft positions, cardinal labels, aircraft nose headings, track vectors and the RGB traffic LEDs all rotate together.

**Joystick Fire** toggles between normal north-up and heading-up mode.

Before using heading-up for the first time, calibrate the zero direction:

1. Use a known compass and point the **top of the Spaceagon north**.
2. Press and hold **Joystick Fire** for at least about 1.2 seconds.
3. Plane Radar stores that magnetometer reading as north and enables heading-up mode.

A short Fire press then toggles heading-up on/off while preserving the calibration.

### Manual badge bearing

The original Tildagon can also align the radar without a compass. Open **Radar Options > Bearing** and enter the compass direction in which the top of the badge is pointing, from `0` through `359` degrees. For example, enter `320` when the top is pointing north-west at 320 degrees. The value is saved and rotates the screen, cardinal points, traffic vectors and LEDs together. Enter `N` in the bearing field to return to north-up. On Spaceagon, performing a new compass calibration clears the manual value and returns control to the magnetometer.

> Compass support is deliberately marked experimental until it has been checked on physical Spaceagon hardware. The current implementation uses the raw horizontal magnetometer axes plus the saved north offset; we may need to adjust axis direction or add fuller hard-iron calibration after real-badge testing.

## Display behaviour

The default radar remains north-up. It preserves the range rings, track/speed vectors and off-scale direction dots. Large colour-matched labels show callsigns and available route codes, while brighter fading trails retain up to twenty recent positions and survive short gaps in the live feed. The bottom card reports the current zoom instead of an aircraft count, and an empty radar gains a brighter green on-screen sweep.

When the live feed provides classification metadata, commercial/civilian aircraft use a filled triangle, general-aviation aircraft use a hollow diamond, helicopters use a cabin/rotor marker and military aircraft use a broad delta. Military and rotorcraft metadata takes priority; incomplete metadata falls back safely to the ordinary civilian symbol.

When Spaceagon heading-up is enabled, a cyan `HDG` marker and numeric heading appear on screen. A saved manual alignment uses `BRG` instead. `SP` indicates that Spaceagon-only controls are available. The local location marker shows `GPS`, `MAN` or `NO LOC`; while following a flight it changes to `FLT`.

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

## App Store package

`tildagon.toml` declares Wi-Fi plus optional Position-provider, RGB-hexpansion and 2026-frontboard enhancements. Release tags match the metadata version; for example, app version `0.1.2` is published as `v0.1.2`.

The original C++ firmware remains in this fork to preserve upstream history and attribution, while `.gitattributes` excludes the original development tree and host tests from Tildagon release archives.

### Replacing a manually copied test version

If Plane Radar was previously copied to `/apps/plane_radar` with `mpremote`, remove that development folder before installing the App Store version:

```powershell
python -m mpremote connect COM6 fs rm -r :/apps/plane_radar
python -m mpremote connect COM6 reset
```

This removes only the manually copied app folder. Plane Radar's saved settings are held by Tildagon's settings service and are left intact. After the reset, install Plane Radar normally from the App Store.

## Current differences from the ESP32-C3 firmware

The Tildagon port does not yet include the embedded major-airport runway overlay or the original browser configuration portal. The portal is unnecessary because Tildagon already manages Wi-Fi and app settings. The runway overlay can be ported independently later.

Network requests currently use Tildagon's synchronous `requests` module, so a slow HTTPS request may briefly pause the UI during a poll.

## Data and attribution

Plane Radar was created by **MatixYo**. This Tildagon edition is a port of
[MatixYo/ESP32-Plane-Radar](https://github.com/MatixYo/ESP32-Plane-Radar),
shared under the MIT licence. We are grateful to MatixYo for making the
original project available for others to enjoy, learn from and adapt. The
original copyright and licence notice remain in [`LICENSE`](LICENSE).

The Tildagon port was adapted by **Mark Brown**, with design, implementation,
testing and documentation assistance from **OpenAI Codex**. AI assistance does
not replace or diminish the original project's authorship or licence.

Live aircraft data comes from adsb.fi. Route labels and Follow Flight use
adsbdb.com when available to resolve origin and destination metadata. Route
results are kept only in a small temporary session cache for display; they are
not republished or incorporated into a database. Location lookups may use
BeaconDB and Postcodes.io.
