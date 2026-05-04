# ESP32 Grove Gesture Control for DiashowDL

This Arduino project allows you to control a DiashowDL Display Server using
hand gestures via an ESP32 and a Grove Gesture v1.0 sensor.

## Hardware Requirements

- **ESP32** (e.g., NodeMCU, DevKit v1)
- **Grove Gesture v1.0** (PAJ7620U2)
- **Grove Cable or Jumper Wires**

### Wiring (I2C)

| ESP32 Pin | Grove Gesture Pin |
|-----------|-------------------|
| 3.3V      | VCC               |
| GND       | GND               |
| SDA (21)  | SDA               |
| SCL (22)  | SCL               |

## Software Requirements

1. **Arduino IDE** or **VSCode with PlatformIO**
2. **Library**: `Seeed_Arduino_PAJ7620` (Search for "Grove Gesture" in Library Manager)
3. **Board Support**: ESP32 by Espressif

## Configuration (Secrets)

To keep your credentials out of the source code, follow these steps:

1. Copy `secrets.h.example` to `secrets.h`.
2. Edit `secrets.h` and enter your WiFi SSID, Password, the Display Server IP, and your API Key.

**Note:** `secrets.h` is excluded from Git to protect your credentials.

## Gesture Mapping

- **Swipe Left**: Previous Slide (`/api/show/previous`)
- **Swipe Right**: Next Slide (`/api/show/next`)
- **Swipe Up**: Stop Show (`/api/show/stop`)
