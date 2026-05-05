"""
DiashowDL Sensor Node — Raspberry Pi

Implements the DiashowDL Sensor Interface (see docs/sensor.md).
Supports BME680 (IAQ) or SCD30 (CO2) via I2C.

- HTTPS REST API on port 9132
- UDP Discovery on port 9133

Usage:
    cp config.example.json config.json   # edit with your settings
    python3 sensor_node.py
"""

import json
import socket
import sys
import threading
from collections import deque
from pathlib import Path

from flask import Flask, jsonify, request

# -- Ports (from sensor spec) -----------------------------------------------

HTTPS_PORT = 9132
UDP_PORT = 9133

# -- Configuration -----------------------------------------------------------

CONFIG_PATH = Path(__file__).parent / "config.json"


def load_config():
    """Load configuration from config.json."""
    if not CONFIG_PATH.exists():
        print(
            "Error: config.json not found.\n"
            "Copy config.example.json to config.json and edit it."
        )
        sys.exit(1)
    with open(CONFIG_PATH) as f:
        return json.load(f)


# -- Sensor Abstraction ------------------------------------------------------


class BME680Sensor:
    """Reads temperature, humidity, pressure, and IAQ from a BME680."""

    _GAS_BURN_IN = 50
    _HUMIDITY_BASELINE = 40.0
    _HUMIDITY_WEIGHT = 0.25

    def __init__(self, i2c_bus=1):
        import bme680
        from smbus2 import SMBus

        self.sensor = bme680.BME680(bme680.I2C_ADDR_PRIMARY, SMBus(i2c_bus))
        self.sensor.set_humidity_oversample(bme680.OS_2X)
        self.sensor.set_pressure_oversample(bme680.OS_4X)
        self.sensor.set_temperature_oversample(bme680.OS_8X)
        self.sensor.set_filter(bme680.FILTER_SIZE_3)
        self.sensor.set_gas_status(bme680.ENABLE_GAS_MEAS)
        self.sensor.set_gas_heater_temperature(320)
        self.sensor.set_gas_heater_duration(150)
        self._gas_data = deque([0] * self._GAS_BURN_IN, maxlen=self._GAS_BURN_IN)
        self._last_iaq = 0
        self.name = "BME680"

    def read(self):
        """Return full-key readings for the REST API."""
        if not self.sensor.get_sensor_data():
            return None
        data = self.sensor.data
        return {
            "temperature": round(data.temperature, 1),
            "humidity": round(data.humidity, 1),
            "pressure": round(data.pressure, 2),
            "iaq": self._calculate_iaq(
                int(data.gas_resistance), data.humidity
            ),
        }

    def read_discovery(self):
        """Return short-key readings for the UDP discovery response."""
        full = self.read()
        if full is None:
            return {}
        return {
            "temp": full["temperature"],
            "hum": full["humidity"],
            "press": full["pressure"],
            "iaq": full["iaq"],
        }

    def _calculate_iaq(self, gas_resistance, humidity):
        """Calculate IAQ from a rolling gas-resistance baseline and humidity.

        Algorithm ported from dart_periphery BME680 driver.
        Uses a rolling window of 50 readings to establish the gas baseline,
        then scores gas (75%) and humidity (25%) relative to their baselines.
        """
        try:
            self._gas_data.append(gas_resistance)
            gas_baseline = round(sum(self._gas_data) / self._GAS_BURN_IN)

            gas_offset = gas_baseline - gas_resistance
            hum_offset = humidity - self._HUMIDITY_BASELINE

            if hum_offset > 0:
                hum_score = (
                    (100.0 - self._HUMIDITY_BASELINE - hum_offset)
                    / (100.0 - self._HUMIDITY_BASELINE)
                    * (self._HUMIDITY_WEIGHT * 100.0)
                )
            else:
                hum_score = (
                    (self._HUMIDITY_BASELINE + hum_offset)
                    / self._HUMIDITY_BASELINE
                    * (self._HUMIDITY_WEIGHT * 100.0)
                )

            gas_weight = 100.0 - (self._HUMIDITY_WEIGHT * 100.0)
            if gas_offset > 0:
                gas_score = (gas_resistance / gas_baseline) * gas_weight
            else:
                gas_score = gas_weight

            self._last_iaq = round(hum_score + gas_score)
            return self._last_iaq
        except (ZeroDivisionError, ValueError):
            return self._last_iaq


class SCD30Sensor:
    """Reads temperature, humidity, and CO2 from an SCD30."""

    def __init__(self, i2c_bus=1):
        from scd30_i2c import SCD30

        self.sensor = SCD30(bus=i2c_bus)
        self.sensor.set_measurement_interval(2)
        self.sensor.start_periodic_measurement()
        self.name = "SCD30"

    def read(self):
        """Return full-key readings for the REST API."""
        if not self.sensor.get_data_ready():
            return None
        m = self.sensor.read_measurement()
        if m is None:
            return None
        return {
            "temperature": round(m[0], 1),
            "humidity": round(m[2], 1),
            "co2": round(m[1], 1),
        }

    def read_discovery(self):
        """Return short-key readings for the UDP discovery response."""
        full = self.read()
        if full is None:
            return {}
        return {
            "temp": full["temperature"],
            "hum": full["humidity"],
            "co2": full["co2"],
        }


SENSOR_CLASSES = {
    "BME680": BME680Sensor,
    "SCD30": SCD30Sensor,
}

# -- Helpers -----------------------------------------------------------------


def get_local_ip():
    """Determine the local network IP address."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    finally:
        s.close()


# -- UDP Discovery -----------------------------------------------------------


def udp_discovery_listener(sensor, hostname):
    """Listen for DIASHOW_SCAN broadcasts and reply with sensor info."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("", UDP_PORT))
    print(f"UDP discovery listening on port {UDP_PORT}")

    while True:
        data, addr = sock.recvfrom(1024)
        msg = data.decode("utf-8", errors="ignore").strip()
        if msg != "DIASHOW_SCAN":
            continue

        response = {
            "type": sensor.name,
            "host": hostname,
            "ip": get_local_ip(),
            "port": HTTPS_PORT,
        }
        response.update(sensor.read_discovery())
        sock.sendto(json.dumps(response).encode(), addr)


# -- Flask REST API ----------------------------------------------------------

app = Flask(__name__)

_sensor = None
_api_key = ""
_hostname = ""


@app.route("/", methods=["GET"])
def get_sensor_data():
    """Return current sensor readings as JSON."""
    if request.headers.get("X-Api-Key") != _api_key:
        return "", 401

    data = _sensor.read()
    if data is None:
        return jsonify({"error": "Sensor read failed"}), 503

    response = {"sensor": _sensor.name, "host": _hostname}
    response.update(data)
    return jsonify(response)


# -- Main --------------------------------------------------------------------


def main():
    global _sensor, _api_key, _hostname

    config = load_config()
    _api_key = config["api_key"]
    sensor_type = config.get("sensor", "BME680").upper()
    _hostname = config.get("hostname", "") or socket.gethostname()
    i2c_bus = config.get("i2c_bus", 1)
    ssl_cert = config.get("ssl_cert", "cert.pem")
    ssl_key = config.get("ssl_key", "key.pem")

    if sensor_type not in SENSOR_CLASSES:
        print(f"Error: Unknown sensor type '{sensor_type}'.")
        print(f"Supported: {', '.join(SENSOR_CLASSES)}")
        sys.exit(1)

    print(f"Initializing {sensor_type} sensor on /dev/i2c-{i2c_bus}...")
    _sensor = SENSOR_CLASSES[sensor_type](i2c_bus=i2c_bus)

    # Start UDP discovery in a background thread
    udp_thread = threading.Thread(
        target=udp_discovery_listener,
        args=(_sensor, _hostname),
        daemon=True,
    )
    udp_thread.start()

    # Start HTTPS server
    print(f"HTTPS server on port {HTTPS_PORT}")
    app.run(
        host="0.0.0.0",
        port=HTTPS_PORT,
        ssl_context=(ssl_cert, ssl_key),
    )


if __name__ == "__main__":
    main()
