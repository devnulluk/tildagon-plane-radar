# Plane Radar roadmap / TODO

This is a research and ideas backlog for optional hardware support. Nothing here should become a hard dependency: Plane Radar should remain fully usable on a base Tildagon, with Hexpansions detected at runtime and used only when they provide a meaningful enhancement.

## Integration principles

- [ ] Prefer generic Tildagon **Capabilities** over hardware-specific code wherever a suitable capability exists.
- [ ] Detect optional hardware at runtime; always preserve the base radar when it is absent.
- [ ] Handle hot-plug and removal gracefully where practical.
- [ ] Lease shared hardware cleanly (`led_owner`, event-bus APIs, etc.) and restore previous state on exit/minimise.
- [ ] Prefer published event-bus/capability interfaces over importing another app's private internals.
- [ ] Make noisy output (speech, haptics, audio, very bright LEDs) independently opt-in/configurable.
- [ ] Do not integrate unrelated hardware merely to increase the supported-Hexpansion count.
- [ ] Investigate proposing a generic matrix/display Capability if the ecosystem does not already have one.

---

## Priority A — make these excellent

### Matrix Hexpansion — Kristian Hentschel

Research references:
- `kristianhentschel/tildagon-matrix-hexpansion`
- `kristianhentschel/tildagon-matrix-hexpansion-app`
- Current LiteLoop implementation exposes a **9 × 18 logical matrix with 156 physical LEDs**.
- Companion app exposes `matrix-hexpansion:display-text` and `matrix-hexpansion:clear-text` event-bus interfaces.
- Board implementation supports on/off images, per-LED PWM brightness, text and patterns.
- Companion app can span/scroll text across multiple attached Matrix Hexpansions.

Ideas:
- [ ] **Mini secondary radar:** followed/own centre in the middle, nearby traffic plotted on the 18×9 grid, brightness used for range/priority.
- [ ] **ATC strip / callsign ticker:** selected/followed callsign, altitude, speed and route (`BAW123 31K 450KT LHR>JFK`). Prefer the existing display-text event for the simplest integration.
- [ ] **Follow Flight route progress:** origin → moving aircraft → destination across the matrix.
- [ ] **Traffic-density scope:** coarse bearing/range bins when 18×9 is too small for individual labels.
- [ ] **Selected-aircraft annunciator:** a Spaceagon touch selection temporarily sends callsign/altitude to the matrix.
- [ ] **Signal-loss/search animation** while reacquiring a followed target.
- [ ] **Multi-matrix cockpit mode:** if several boards are fitted, dedicate one to radar and one to flight strip/data, or concatenate into a wider information display.
- [ ] Research a generic Matrix/Pixel-Display Capability so Plane Radar does not depend directly on LiteLoop internals.
- [ ] Verify colour capability on physical hardware. Current source exposes one brightness byte per LED, so assume monochrome until proven otherwise.

### East Essex Hackspace Logo — HIGH PRIORITY / hardware available for testing

The current EEH software identifies the **EEH Logo as 14 NeoPixels**.

  - [x] **14-pixel Follow Flight progress:** completed green/teal, current segment cyan, remaining dim blue.
  - [x] **Target-lock state:** smooth cyan while locked; smooth red if target is lost; twin chase for emergency focus.
  - [x] **Local traffic meter:** one illuminated pixel per visible aircraft up to 14; overflow shown with a pulse/alternate pattern.
  - [x] **Radar/status animation:** use the logo as a decorative secondary sweep rather than claiming physical bearing until its LED geometry/order is mapped.
- [ ] **Startup/network state:** distinct short animations for GPS acquisition, Wi-Fi and ADS-B connection.
- [ ] **Vertical-rate/altitude mode:** climb/fall animation for a followed aircraft after physical LED ordering is mapped.
  - [x] Respect the existing EEH app's slot/type configuration, avoid its active background controller, and leave its saved effects untouched.
- [ ] If two EEH boards are fitted, support mirror status or split roles (progress on one, status/traffic on the other).
- [ ] Reuse sensible generic states on the related EEH Dalek (3 LEDs), TARDIS (5), K9 (1) and Sonic Screwdriver (1) without pretending they are compass displays.

### Keepdexpansion

- [ ] Refine physical-keyboard Follow Flight entry after hardware testing.
  - [x] Use keyboard backlight for local traffic, special alerts, journey progress and target lock while preserving and restoring the user's existing backlight state.
- [ ] Keyboard shortcuts for Follow Flight, page switching, reacquire, details and stop-follow.
- [ ] One-time keyboard cheat-sheet when Keepdexpansion is first detected.

### GPS / Position / NMEA

- [ ] Keep the generic Position Capability as the normal source for startup position and explicit refresh.
- [ ] Optionally use provider speed/bearing when supplied for diagnostics.
- [ ] Optional NMEA diagnostics: satellites locked, fix quality and UTC. Do not use NMEA instead of Position for normal location.

### Haptic Feedback / Caffeine Jitters

- [ ] `double_click` when Follow Flight locks a target.
- [ ] Subtle `tick` when selected/followed traffic crosses a configurable near-range threshold.
- [ ] Distinct buzz for target loss; softer click on reacquisition.
- [ ] Arrival/approach ramp at a configurable destination threshold.
- [ ] Rate-limit and make each haptic alert independently switchable.

---

## Priority B — displays, storage and audio

### HUB75 Hexpansion

- [ ] Research driver/API and supported external panel sizes.
- [ ] Full-size external airport-radar display while the badge remains the controller.
- [ ] Departure-board style Follow Flight information.
- [ ] Large route-progress / nearby-aircraft desk or event display.

### Screen Hexpansion

- [ ] Research resolution/driver/API.
- [ ] Keep radar on the circular badge and persistent followed-flight data/route on the secondary screen.
- [ ] Or invert roles: details/controls on badge, larger radar/map on the external screen.

### 7-segment display

- [ ] Aircraft count in local radar mode.
- [ ] Follow Flight progress %, flight level or destination range depending on available digits.
- [ ] Blink only for meaningful alerts.

### SD / Dual SD Card

- [ ] Plane-spotting log: timestamp, callsign, Mode-S hex, aircraft type, altitude, range and bearing.
- [ ] Followed-flight breadcrumb tracks for later export/replay.
- [ ] Offline airport/runway database and airline/callsign mappings.
- [ ] Replay recorded flights/radar sessions.
- [ ] Export simple CSV/JSON.

### DECTalk / speech

- [ ] Optional spoken selected-aircraft summary: callsign, altitude, distance and bearing.
- [ ] Speak target acquired/lost, origin/destination and arrival status in Follow Flight.
- [ ] Strong rate limiting and explicit enable setting.

### Headphone / audio-output Hexpansions

- [ ] Optional radar sonification: stereo pan = bearing, pitch = altitude, repetition/volume = range.
- [ ] Quiet target-acquired/lost cues for plane spotting without watching the display.
- [ ] Accessibility mode using tones/speech where a suitable provider exists.

### LED/buzzer/EEPROM Hexpansions

- [ ] Simple target acquired/lost/range-threshold cues where no richer haptic/audio output exists.
- [ ] Morse callsign as an intentionally fun optional mode, never default.

---

## Priority C — sensors, controls and physical indicators

### Grove I/O / Pimoroni Breakout Garden I2C

- [ ] Prefer a generic sensor-provider approach rather than hard-coding every module.
- [ ] Pressure/BME/BMP sensor: show local pressure/QNH and investigate pressure-altitude correction alongside ADS-B barometric altitude.
- [ ] Temperature/humidity: optional environmental details page/footer, not main-radar clutter.
- [ ] Light sensor: automatically reduce Matrix/NeoPixel brightness at night if there is no better OS ambient-light source.
- [ ] Rotary encoder/joystick modules: optional physical zoom/selection controls where useful.

### LEGspansion / servo outputs

- [ ] **Physical aircraft pointer:** servo needle points to selected/followed aircraft bearing.
- [ ] Second servo for altitude/range; third for vertical rate or route progress.
- [ ] Experimental/showpiece only; enforce safe motion limits.

### Badgebot / HEX-DRIVE-V2

- [ ] Explore its servo outputs for a physical bearing pointer.
- [ ] Fun demo: robot rotates to point toward selected aircraft, only if control is safe and predictable.
- [ ] ToF sensor could wake/show details when someone approaches a desk-mounted radar; low priority.

### Spirit-level / orientation hardware

- [ ] If a generic orientation/IMU Capability appears, use it to improve heading-up calibration or warn when badge angle makes compass heading unreliable.

---

## Priority D — communications / networking experiments

### Bleepie paging Hexpansion

- [ ] Research message API.
- [ ] Send selected/followed callsign or target-acquired alerts to another nearby badge.
- [ ] Plane-spotting group mode: one badge spots interesting traffic and pages callsign/bearing to friends.

### Ethernet + PoE Hexpansion

- [ ] Research whether W5500 integrates with the same socket/`requests` stack Plane Radar uses.
- [ ] If practical, support a desk-mounted always-on wired/PoE radar without a separate Plane Radar networking implementation.

### WiFiSpansion

- [ ] Research whether it offers a useful alternate network interface or antenna/range benefit.
- [ ] Avoid special-case networking unless Tildagon OS exposes it cleanly.

### Radiolarian flexible digital radio

- [ ] Research **direct 1090 MHz ADS-B reception feasibility**: RF tuning range, sample bandwidth, demodulation resources and antenna requirements. Do not promise this until verified.
- [ ] If direct ADS-B is unrealistic, investigate receiving a simpler feed/protocol from a nearby external ADS-B receiver.

### IR Tx/Rx

- [ ] Low-priority experiment: IR remote as desk-radar control or send compact selected-flight information between IR-equipped badges.
- [ ] Do not implement unless a real use case survives testing.

---

## Generic lighting ecosystem

Applicable to NeoPixel/Merged-NeoPixel providers and boards such as EEH devices, SK9822, LEDspansion, Too-many-LEDs, Pacman, Monsterspansion and similar, where an appropriate capability/API is available.

- [ ] Define reusable output roles: `bearing`, `progress`, `traffic_count`, `target_state`, `network_state`.
- [ ] Allow/provider-detect geometry classes: radial/spatial, linear or decorative.
- [ ] Use radial layouts for true bearing only when physical geometry is known.
- [ ] Use linear layouts for flight progress, altitude or traffic count.
- [ ] Use decorative layouts for sweep, lock/lost and connection-state animations.
- [x] Restore previous LED owner/pattern on exit where the provider exposes an ownership contract.

---

## Deliberately low priority / do not force an integration

- [ ] Geiger counter — no obvious aviation/radar use; leave alone unless a genuine use case emerges.
- [ ] Microphone / HexyHexyMic / TGSTL — perhaps an optional audio-reactive visual theme eventually, but no always-listening control and no core dependency.
- [ ] Floppy disk, social battery and unrelated novelty hardware — only revisit if a useful data/control story emerges.
- [ ] Purely mechanical/decorative Hexpansions need no software support.

---

## Cross-hardware UX

- [ ] Hardware/Enhancements page showing optional providers currently detected: GPS, Spaceagon, keyboard, matrix, NeoPixels, haptics, storage, etc.
- [ ] Allow each enhancement to be enabled/disabled independently.
- [ ] One-time concise hint when newly detected hardware unlocks a feature (`Matrix detected — using it for flight strip`).
- [ ] Sensible automatic roles with advanced reassignment later.
- [ ] Define ownership/precedence when several output devices are connected so apps do not fight for hardware.

## Research note

The Matrix social post linked from the official Tildagon gallery was not directly fetchable during this research pass. Kristian Hentschel's current hardware and companion-app repositories were inspected instead; those establish the 18×9/156-LED geometry, bitmap/PWM/text control and multi-board behaviour used above.
