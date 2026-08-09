# Plane Radar for Tildagon

This fork adds a native Tildagon/MicroPython version of Plane Radar while leaving the original ESP32-C3/Arduino firmware and upstream history intact.

Plane Radar shows live nearby aircraft from the adsb.fi v3 API on the badge's round display, with a radar-style LED ring. It works on the original 2024 Tildagon and automatically unlocks extra controls when a 2026 Spaceagon frontboard is fitted.

## First start

The first launch opens with an animated radar boot screen and an on-badge QR code. Scan it to return to these instructions, or press **OK** while the splash is visible for a larger QR help screen.

The first-run splash remains visible for a few seconds so there is time to scan it. Later launches use a shorter animated splash.

## Location

Plane Radar checks for a location provider **once when it starts**. It prefers Tildagon's optional Position capability, so a compatible GPS hexpansion can supply the radar centre without any app-specific configuration.

For compatibility with older GPS EEPROM firmware, Plane Radar also checks active hexpansion apps for a valid `position` property even when they do not advertise the newer capability.

The chosen location remains fixed while the radar runs; it does not continuously follow GPS. Press **Down** whenever you want to request a fresh GPS fix. If no new fix is available, the existing radar centre is retained.

A manually entered latitude/longitude can be saved at any time with **OK/Confirm** and remains available when no GPS fix is present.

## Standard controls

These controls work on both 2024 Tildagon and 2026 Spaceagon. The Spaceagon joystick direction inputs map to the same standard controls.

| Control | Action |
|---|---|
| Right | Cycle 5 / 10 / 15 / 25 km range |
| Left | Refresh aircraft immediately |
| Up | Toggle kilometres / miles |
| Down | Request a new GPS position |
| OK / Confirm | Edit and save manual latitude / longitude |
| Cancel / Back | Minimise Plane Radar |

## RGB LED radar

While Plane Radar is foregrounded it temporarily takes control of Tildagon's 12 onboard RGB LEDs:

- a green sweep rotates clockwise around the badge;
- aircraft illuminate the LED sector matching their bearing on the radar;
- closer in-range aircraft appear brighter red/magenta;
- off-scale aircraft remain visible as dim magenta bearing cues;
- a subtle blue marker across the top LED pair indicates a GPS-derived radar centre.

When Plane Radar is minimised or terminated it restores the normal Tildagon LED pattern.

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

When Spaceagon heading-up is enabled, a cyan `HDG` marker and numeric heading appear on screen. `SP` indicates that Spaceagon-only controls are available. The location marker shows `GPS`, `MAN` or `NO LOC`.

## Host-side tests

The geometry, ADS-B parsing, GPS validation, LED mapping and Spaceagon helper functions can be tested without badge hardware:

```sh
python -m unittest discover -s tests -v
```

The app source can also be syntax checked with standard Python:

```sh
python -m py_compile app.py adsb.py radar_math.py location_provider.py led_radar.py spaceagon.py instructions_qr.py
```

## Publishing

`tildagon.toml` declares Wi-Fi plus optional Position-provider and 2026-frontboard enhancements. Before the first app-store release, add the repository topic `tildagon-app` and create a release/tag matching the metadata version (initially `v0.1.0`).

The original C++ firmware remains in this fork to preserve upstream history and attribution, while `.gitattributes` excludes the original development tree and host tests from Tildagon release archives.

## Current differences from the ESP32-C3 firmware

The Tildagon port does not yet include the embedded major-airport runway overlay or the original browser configuration portal. The portal is unnecessary because Tildagon already manages Wi-Fi and app settings. The runway overlay can be ported independently later.

Network requests currently use Tildagon's synchronous `requests` module, so a slow HTTPS request may briefly pause the UI during a poll.

## Attribution

Original Plane Radar project: **MatixYo/ESP32-Plane-Radar**, MIT licensed. This port retains the same licence and uses the same adsb.fi data source as upstream.
