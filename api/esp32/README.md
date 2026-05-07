# DiashowDL ESP32 Controllers

Arduino sketches that turn an ESP32 into a physical presenter remote for the
DiashowDL Display Server. Each sketch connects to WiFi and drives playback
over the REST API on port `9134`.

## Sketches

| Sketch | Input | Mapping |
|--------|-------|---------|
| [`buttons/`](buttons/) | Two GPIO push-buttons | Previous / Next |
| [`grove_gesture/`](grove_gesture/) | Seeed Grove Gesture v1.0 (PAJ7620U2) | Swipe Left / Right / Up |

See each sub-directory's `README.md` for wiring details and gesture
mappings.

## Hardware Requirements

- **ESP32** (e.g., NodeMCU, DevKit v1)
- Sketch-specific peripheral (push-buttons or Grove Gesture sensor)
- USB cable for flashing

## Software Requirements

1. **Arduino IDE** or **VSCode with PlatformIO**
2. **Board Support**: ESP32 by Espressif
3. **Sketch-specific libraries** (see each sub-directory's README)

## Configuration (Secrets)

Both sketches read WiFi and API credentials from a `secrets.h` file that is
not checked into Git. For each sketch you flash:

1. Copy `secrets.h.example` to `secrets.h` in the same directory.
2. Fill in your WiFi SSID, password, the Display Server IP, and your API key.

**Note:** `secrets.h` is excluded from Git to protect your credentials.

## TLS

The Display Server uses a device-unique self-signed certificate. The sketches
connect with `WiFiClientSecure::setInsecure()` — appropriate for LAN use
against a known display IP, but do not reuse this pattern for general-purpose
HTTPS clients.
