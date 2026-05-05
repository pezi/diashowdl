# ESP32 Sensor Node for DiashowDL

This Arduino project implements the DiashowDL
[Sensor Interface](../../../docs/sensor.md) on an ESP32 with either a
BME680 or SCD30 I2C sensor. The Diashow App discovers
this node via UDP broadcast and polls it for environment data over HTTPS.

## Hardware Requirements

- **ESP32** (e.g., NodeMCU, DevKit v1)
- **BME680** breakout (temperature, humidity, pressure, IAQ) **or**
  **SCD30** module (temperature, humidity, CO2)

### Wiring (I2C)

| ESP32 Pin | Sensor Pin |
|-----------|------------|
| 3.3V      | VCC        |
| GND       | GND        |
| GPIO 21   | SDA        |
| GPIO 22   | SCL        |

## Software Requirements

1. **Arduino IDE** or **VSCode with PlatformIO**
2. **Board Support**: ESP32 by Espressif
3. **Libraries** (install via Library Manager):
   - `ArduinoJson` by Benoit Blanchon
   - `Adafruit BME680 Library` (if using BME680)
   - `SparkFun SCD30 Arduino Library` (if using SCD30)

## Configuration

### 1. Secrets

1. Copy `secrets.h.example` to `secrets.h`.
2. Edit `secrets.h` and enter your WiFi SSID, Password, and the API Key
   that clients (the Diashow App) must present.

**Note:** `secrets.h` is excluded from Git to protect your credentials.

### 2. Sensor Selection

Open `sensor_node.ino` and change the `ACTIVE_SENSOR` define:

```cpp
#define ACTIVE_SENSOR SENSOR_BME680   // or SENSOR_SCD30
```

## How It Works

- **UDP Discovery (port 9133):** Responds to `DIASHOW_SCAN` broadcasts
  with a JSON packet containing the sensor type, IP, port, and current
  readings.
- **HTTPS REST API (port 9132):** Serves `GET /` with full sensor data
  over TLS (mbedTLS). Requires the `X-Api-Key` header to match the
  configured key.

### SSL/TLS

The certificate and private key are stored in `secrets.h` as
`SERVER_CERT` and `SERVER_KEY`. Run the provided script to generate
them automatically:

```bash
cp secrets.h.example secrets.h   # if not done already
./generate_cert.sh
```

This generates a self-signed RSA-2048 certificate (valid 10 years) and
writes it into `secrets.h` in the correct C string format.

## Testing

```bash
curl -k -H "X-Api-Key: your-sensor-api-key" https://<esp32-ip>:9132/
```

## IAQ Calculation

The BME680 IAQ score is computed using a rolling-baseline algorithm
(ported from [dart_periphery](https://pub.dev/packages/dart_periphery)).
It maintains a window of 50 gas resistance readings to establish a
baseline, then scores gas (75%) and humidity (25%) relative to their
baselines. The score stabilizes after approximately 50 readings.
