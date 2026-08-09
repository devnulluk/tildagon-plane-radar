# Tildagon port

This fork adds a native Tildagon/MicroPython version of Plane Radar while leaving the original ESP32-C3/Arduino firmware intact.

The port keeps the original project's core behaviour: a north-up round radar, live aircraft from the adsb.fi v3 API, 5/10/15/25 km presets, heading triangles, track/speed vectors, callsign and altitude labels, off-scale direction dots, km/miles and automatic polling.

Tildagon manages Wi-Fi, so the Arduino WiFiManager captive portal is not needed. Range, units and a manual fallback location are stored through Tildagon's `settings` module.

## Location

Plane Radar checks Tildagon's optional **Position capability once when the app starts**. If a running GPS hexpansion or another app provides a valid `(latitude, longitude)` position, that fix becomes the radar centre and the display shows `GPS`.

For compatibility with older GPS EEPROM firmware, Plane Radar also checks active hexpansion apps for a valid `position` property even when they do not yet advertise the Position capability.

GPS is deliberately **not polled continuously**. The radar centre stays fixed until the user asks for another fix with **Down** (or joystick down on a Spaceagon). If the refresh cannot obtain a fix, the existing radar centre is retained rather than being replaced unexpectedly.

A manually entered latitude/longitude remains stored and can be selected at any time with Confirm/OK. If no GPS fix and no manual location are available, the app offers manual setup.

## RGB LED radar

While Plane Radar is in the foreground it temporarily takes control of Tildagon's 12 onboard RGB LEDs and turns them into an outer radar ring:

- a green sweep rotates clockwise around the badge;
- aircraft illuminate the LED sector matching their bearing from the radar centre;
- nearer in-range aircraft appear brighter red/magenta;
- off-scale aircraft remain as dim magenta bearing cues;
- a subtle blue marker across the top pair indicates that the radar centre currently comes from GPS.

The normal Tildagon LED pattern is restored when Plane Radar is minimised or terminated.

## Controls

| Button | Action |
|---|---|
| Right | Cycle 5 / 10 / 15 / 25 km range |
| Left | Refresh aircraft now |
| Up | Toggle kilometres / miles |
| Down | Request a fresh GPS/Position fix |
| Confirm / OK | Edit/save manual latitude and longitude |
| Cancel / Back | Minimise Plane Radar |

On the Spaceagon, the 5-way joystick automatically provides the same generic Up/Down/Left/Right/Confirm controls.

## Host-side tests

The geometry, ADS-B parsing, GPS validation and LED-bearing helpers do not depend on Tildagon modules:

```sh
python -m unittest discover -s tests -v
```

## Publishing

The repository includes `tildagon.toml` for Tildagon packaging and declares the Position capability as an optional enhancement. Before the first app-store release, add the repository topic `tildagon-app` and create a release/tag matching the metadata version (initially `v0.1.0`).

The original C++ firmware remains in this fork to preserve upstream history and attribution, while `.gitattributes` excludes it from release archives intended for the badge.

## Current differences from ESP32-C3 firmware

The first Tildagon port does not yet include the embedded major-airport runway overlay or browser configuration portal. The portal is unnecessary because Tildagon already provides Wi-Fi and app settings. A runway overlay can be added independently later.

Network requests use Tildagon's synchronous `requests` module, so a slow HTTPS request may briefly pause the UI during a poll.

## Attribution

Original Plane Radar project: MatixYo/ESP32-Plane-Radar, MIT licensed. The Tildagon port retains the same licence and uses the same adsb.fi data source as upstream.
