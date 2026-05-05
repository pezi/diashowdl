# Sensor Node for DiashowDL (Dart)

This Dart CLI implements the DiashowDL
[Sensor Interface](../../../docs/sensor.md) on Linux single-board computers
using the [dart_periphery](https://pub.dev/packages/dart_periphery) package
for I2C sensor access. Supports BME680 and SCD30.

## Supported Platforms

| Board              | I2C Bus (`i2c_bus` in config) |
|--------------------|-------------------------------|
| Raspberry Pi       | `1` (default)                 |
| NanoPi (Armbian)   | `0`                           |
| Banana Pi (Armbian) | `2`                          |

## Hardware Requirements

- **Linux SBC** with I2C support (see table above)
- **BME680** breakout (temperature, humidity, pressure, IAQ) **or**
  **SCD30** module (temperature, humidity, CO2)

### Wiring (I2C)

| SBC Pin    | Sensor Pin |
|------------|------------|
| 3.3V       | VCC        |
| GND        | GND        |
| SDA        | SDA        |
| SCL        | SCL        |

Enable I2C on Raspberry Pi:

```bash
sudo raspi-config   # Interface Options > I2C > Enable
```

## Software Setup

```bash
# Install Dart SDK (if not already installed)
# See https://dart.dev/get-dart

# Install dependencies
dart pub get

# Copy and edit configuration
cp config.example.json config.json
# Edit config.json: set api_key, sensor type, hostname, and i2c_bus
```

### SSL Certificates

Generate a self-signed certificate for HTTPS:

```bash
openssl req -x509 -nodes -days 3650 -newkey rsa:2048 \
  -keyout key.pem -out cert.pem -subj "/CN=DiashowSensor"
```

## Usage

```bash
dart run bin/sensor_node.dart
```

### Compile to Native Binary

```bash
dart compile exe bin/sensor_node.dart -o sensor_node
./sensor_node
```

## Testing

```bash
curl -k -H "X-Api-Key: your-sensor-api-key" https://localhost:9132/
```
