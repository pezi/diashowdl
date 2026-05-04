# Diashow App Sensor Interface Specification

This document describes the interface between the Diashow App and environment sensors (e.g., BME680, SCD30). By implementing this interface on hardware like an ESP32 or a Raspberry Pi, the Diashow App can discover and display real-time sensor data within its presentations.

## 1. Network Architecture

The sensor node provides two network services:
1.  **UDP Discovery:** Listens on port **9133** for broadcast requests to help the app find the sensor on the local network.
2.  **REST API:** Provides sensor data via HTTPS on port **9132**.

## 2. UDP Discovery Interface

To simplify integration, the Diashow App scans the network using UDP broadcast.

-   **Discovery Port:** 9133
-   **Discovery Trigger:** The app sends the string `DIASHOW_SCAN` as a UDP broadcast to `255.255.255.255:9133`.
-   **Sensor Response:** The sensor node must respond with a JSON packet (UDP unicast back to the requester's IP and port).

### Discovery Response JSON Format

```json
{
  "type": "BME680",
  "host": "ESP32",
  "ip": "192.168.1.100",
  "port": 9132,
  "temp": 22.5,
  "hum": 45.0,
  "press": 1013.25,
  "iaq": 25
}
```

| Field | Type | Description |
| :--- | :--- | :--- |
| `type` | string | Sensor model (e.g., "BME680", "SCD30"). |
| `host` | string | User-defined host name of the sensor node. |
| `ip` | string | The IP address where the REST API is listening. |
| `port` | number | The REST API port (default: 9132). |
| `temp` | number | Current temperature in Celsius (optional). |
| `hum` | number | Current relative humidity in % (optional). |
| `press` | number | Current air pressure in hPa (optional). |
| `iaq` | number | Indoor Air Quality index (optional). |
| `co2` | number | CO2 level in ppm (optional). |

---

## 3. REST API Interface

The main sensor data is fetched via a REST call over HTTPS.

-   **Endpoint:** `GET /`
-   **Port:** 9132
-   **Protocol:** HTTPS (Self-signed certificates are allowed but must be trusted or accepted by the app's environment).

### Authentication

All requests MUST include an API Key in the HTTP headers for security.

-   **Header Key:** `X-Api-Key`
-   **Required Value:** The user-configured API key from the Diashow App settings (*General > API Key*). Both the sensor node and the app must use the same key.

### REST Response JSON Format

```json
{
  "sensor": "BME680",
  "host": "ESP32",
  "temperature": 22.5,
  "humidity": 45.0,
  "pressure": 1013.25,
  "iaq": 25,
  "co2": 400.0
}
```

| Field | Type | Description |
| :--- | :--- | :--- |
| `sensor` | string | Sensor model (e.g., "BME680"). |
| `host` | string | User-defined host name of the sensor node. |
| `temperature` | number | Temperature in Celsius. |
| `humidity` | number | Relative humidity in %. |
| `pressure` | number | Air pressure in hPa. |
| `iaq` | number | Indoor Air Quality index (0–500). |
| `co2` | number | CO2 level in ppm. |

*Note: The sensor should only include fields it actually supports.*

---

## 4. Indoor Air Quality (IAQ) and CO2 Classification

The app classifies air quality based on the following thresholds:

### IAQ Index (e.g., BME680)
-   **Excellent:** 0 - 50
-   **Good:** 51 - 100
-   **Fair:** 101 - 150
-   **Poor:** 151 - 200
-   **Bad:** 201 - 300
-   **Very Bad:** > 300

### CO2 Level (e.g., SCD30)
-   **Excellent:** < 600 ppm
-   **Good:** 600 - 1000 ppm
-   **Fair:** 1001 - 1500 ppm
-   **Poor:** 1501 - 2500 ppm
-   **Bad:** > 2500 ppm

---

## 5. DDL Integration

To display the sensor data in a Diashow, use the `sensor` widget in your DDL file.

```json
{
  "name": "sensor",
  "parameter": {
    "color": "#FFFFFF",
    "temperature": "c",
    "pressure": true,
    "humidity": true,
    "iaq": true,
    "refresh": 60
  }
}
```

| Parameter | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `color` | string | `"#FFFFFF"` | Text color (hex). |
| `temperature` | string | `"c"` | Unit format: `"c"` for Celsius, `"f"` for Fahrenheit. |
| `pressure` | bool | `true` | Show air pressure reading. |
| `humidity` | bool | `true` | Show humidity reading. |
| `iaq` | bool | `true` | Show air quality (IAQ index or CO2 level, depending on the connected sensor). |
| `refresh` | int | `60` | Poll interval in seconds (clamped to 15–3600). |

*Note: The sensor URL is provided automatically by the app based on the user's selection in settings or by the display server. It cannot be set in the DDL file.*

---

## 6. Simulated Sensor

The app includes a built-in simulated sensor for testing without hardware. Select "Simulated" in the sensor settings to start a local HTTP server on port 9132 that returns randomized BME680-style readings.

---

## 7. Reference Implementations

Ready-to-use implementations are in `tools/sensor/`:

| Platform | Path | Sensor Access |
| :--- | :--- | :--- |
| ESP32 (Arduino) | `tools/sensor/esp32/` | Adafruit BME680 / SparkFun SCD30, HTTPS via mbedTLS |
| Linux SBC (Dart) | `tools/sensor/dart/` | [dart_periphery](https://pub.dev/packages/dart_periphery), compilable to native binary |
| Linux SBC (Python) | `tools/sensor/python/` | Flask HTTPS server, `bme680` / `scd30-i2c` packages |
| Linux SBC (Rust) | `tools/sensor/rust/` | `bme680` crate + `linux-embedded-hal`, axum HTTPS server |
| Linux SBC (Go) | `tools/sensor/go/` | `periph.io` for I2C, native HTTPS server |

Each implementation provides the full sensor interface: UDP discovery on port 9133 and HTTPS REST API on port 9132 with `X-Api-Key` authentication.

---
*Created: March 2026*
