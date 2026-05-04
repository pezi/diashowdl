# ESP32 Button Control for DiashowDL

This Arduino project allows you to control a DiashowDL Display Server using
two physical buttons connected to an ESP32.

## Hardware Requirements

- **ESP32** (e.g., NodeMCU, DevKit v1)
- **2x Push Buttons**
- **Breadboard and Jumper Wires**

### Wiring (Active High)

Connect the buttons such that they pull the pin towards 3.3V when pressed.

| ESP32 Pin | Button Function | Wiring |
|-----------|-----------------|--------|
| GPIO 32   | Previous Slide  | Button -> GND |
| GPIO 33   | Next Slide      | Button -> GND |

## Software Requirements

1. **Arduino IDE** or **VSCode with PlatformIO**
2. **Board Support**: ESP32 by Espressif

## Configuration (Secrets)

To keep your credentials out of the source code, follow these steps:

1. Copy `secrets.h.example` to `secrets.h`.
2. Edit `secrets.h` and enter your WiFi SSID, Password, the Display Server IP, and your API Key.

**Note:** `secrets.h` is excluded from Git to protect your credentials.

## Logic

This project uses `digitalRead` with `INPUT_PULLUP` to detect button presses.
Buttons are wired between the GPIO pin and GND — pressing a button pulls the
pin LOW. A rising-edge detection with 300 ms debounce triggers the API call.
