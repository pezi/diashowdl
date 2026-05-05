# Sensor Node for DiashowDL (Python)

This Python script implements the DiashowDL
[Sensor Interface](../../../docs/sensor.md) on single-board computers with
either a BME680 or SCD30 I2C sensor. The Diashow App discovers this node via
UDP broadcast and polls it for environment data over HTTPS.

## Supported Platforms

| Board | I2C Bus (`i2c_bus` in config) |
|-------|-------------------------------|
| Raspberry Pi | `1` (default) |
| NanoPi (Armbian) | `0` |
| Banana Pi (Armbian) | `2` |

## Hardware Requirements

- **Single-board computer** with I2C support (see table above)
- **BME680** breakout (temperature, humidity, pressure, IAQ) **or**
  **SCD30** module (temperature, humidity, CO2)

### Wiring (I2C)

| Pi Pin     | Sensor Pin |
|------------|------------|
| 3.3V (Pin 1) | VCC     |
| GND (Pin 6)  | GND     |
| GPIO 2 (Pin 3) | SDA   |
| GPIO 3 (Pin 5) | SCL   |

Enable I2C on the Pi:

```bash
sudo raspi-config   # Interface Options > I2C > Enable
```

## Software Setup

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Copy and edit configuration
cp config.example.json config.json
# Edit config.json: set api_key, sensor type, and i2c_bus for your board
```

### SSL Certificates

Generate a self-signed certificate for HTTPS:

```bash
openssl req -x509 -nodes -days 3650 -newkey rsa:2048 \
  -keyout key.pem -out cert.pem -subj "/CN=DiashowSensor"
```

The generated `cert.pem` and `key.pem` are referenced in `config.json`
and excluded from Git.

## Usage

```bash
source venv/bin/activate
python3 sensor_node.py
```

## Testing

```bash
curl -k -H "X-Api-Key: your-sensor-api-key" https://localhost:9132/
```

## Running as a Service (optional)

Create `/etc/systemd/system/diashow-sensor.service`:

```ini
[Unit]
Description=DiashowDL Sensor Node
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/diashow-sensor
ExecStart=/home/pi/diashow-sensor/venv/bin/python3 sensor_node.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Then enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable diashow-sensor
sudo systemctl start diashow-sensor
```

## IAQ Calculation

The BME680 IAQ score is computed using a rolling-baseline algorithm
(ported from [dart_periphery](https://pub.dev/packages/dart_periphery)).
It maintains a window of 50 gas resistance readings to establish a
baseline, then scores gas (75%) and humidity (25%) relative to their
baselines. The score stabilizes after approximately 50 readings.
