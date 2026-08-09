# Tildagon port

This fork adds a native Tildagon/MicroPython version of Plane Radar while leaving the original ESP32-C3/Arduino firmware intact.

The port keeps the original project's core behaviour: a north-up round radar, live aircraft from the adsb.fi v3 API, 5/10/15/25 km presets, heading triangles, track/speed vectors, callsign and altitude labels, off-scale direction dots, km/miles and automatic polling.

Tildagon manages Wi-Fi, so the Arduino WiFiManager captive portal is not needed. Latitude, longitude, range and units are stored through Tildagon's `settings` module.

## Controls

| Button | Action |
|---|---|
| Right | Cycle 5 / 10 / 15 / 25 km range |
| Left | Refresh aircraft now |
| Up | Toggle kilometres / miles |
| Confirm / OK | Edit radar latitude and longitude |
| Cancel / Back | Minimise Plane Radar |

On first launch the app asks for latitude and longitude as decimal coordinates.

## Host-side tests

The geometry and ADS-B parsing helpers do not depend on Tildagon modules:

```sh
python -m unittest discover -s tests -v
```

## Publishing

The repository includes `tildagon.toml` for Tildagon packaging. Before the first app-store release, add the repository topic `tildagon-app` and create a release/tag matching the metadata version (initially `v0.1.0`).

The original C++ firmware remains in this fork to preserve upstream history and attribution, while `.gitattributes` excludes it from release archives intended for the badge.

## Current differences from ESP32-C3 firmware

The first Tildagon port does not yet include the embedded major-airport runway overlay or browser configuration portal. The portal is unnecessary because Tildagon already provides Wi-Fi and app settings. A runway overlay can be added independently later.

Network requests use Tildagon's synchronous `requests` module, so a slow HTTPS request may briefly pause the UI during a poll.

## Attribution

Original Plane Radar project: MatixYo/ESP32-Plane-Radar, MIT licensed. The Tildagon port retains the same licence and uses the same adsb.fi data source as upstream.
