/// DiashowDL Sensor Node — Rust CLI
///
/// Implements the DiashowDL Sensor Interface (see docs/sensor.md).
/// Supports BME680 (IAQ) or SCD30 (CO2) via I2C.
///
/// - HTTPS REST API on port 9132
/// - UDP Discovery on port 9133
///
/// Usage:
///     cp config.example.json config.json
///     cargo run --release
#[cfg(target_os = "linux")]
use std::collections::VecDeque;
use std::fs;
use std::net::SocketAddr;
use std::process;
use std::sync::{Arc, Mutex};

use axum::extract::State;
use axum::http::{HeaderMap, StatusCode};
use axum::response::Json;
use axum::routing::get;
use axum::Router;
use axum_server::tls_rustls::RustlsConfig;
use serde::Deserialize;
use serde_json::{json, Value};
use tokio::net::UdpSocket;

// -- Ports (from sensor spec) ------------------------------------------------

const HTTPS_PORT: u16 = 9132;
const UDP_PORT: u16 = 9133;

// -- Configuration -----------------------------------------------------------

#[derive(Deserialize)]
struct Config {
    api_key: String,
    #[serde(default = "default_sensor")]
    sensor: String,
    #[serde(default)]
    hostname: String,
    #[serde(default = "default_i2c_bus")]
    i2c_bus: u8,
    #[serde(default = "default_ssl_cert")]
    ssl_cert: String,
    #[serde(default = "default_ssl_key")]
    ssl_key: String,
}

fn default_sensor() -> String {
    "BME680".to_string()
}
fn default_i2c_bus() -> u8 {
    1
}
fn default_ssl_cert() -> String {
    "cert.pem".to_string()
}
fn default_ssl_key() -> String {
    "key.pem".to_string()
}

fn load_config() -> Config {
    let text = match fs::read_to_string("config.json") {
        Ok(t) => t,
        Err(_) => {
            eprintln!(
                "Error: config.json not found.\n\
                 Copy config.example.json to config.json and edit it."
            );
            process::exit(1);
        }
    };
    match serde_json::from_str(&text) {
        Ok(c) => c,
        Err(e) => {
            eprintln!("Error parsing config.json: {e}");
            process::exit(1);
        }
    }
}

// -- Sensor Abstraction ------------------------------------------------------

trait Sensor: Send + Sync {
    fn name(&self) -> &str;

    /// Return full-key readings for the REST API.
    fn read(&mut self) -> Option<Value>;

    /// Return short-key readings for the UDP discovery response.
    fn read_discovery(&mut self) -> Value;
}

// -- BME680 IAQ Constants ----------------------------------------------------

#[cfg(target_os = "linux")]
const GAS_BURN_IN: usize = 50;
#[cfg(target_os = "linux")]
const HUMIDITY_BASELINE: f64 = 40.0;
#[cfg(target_os = "linux")]
const HUMIDITY_WEIGHT: f64 = 0.25;

#[cfg(target_os = "linux")]
fn calculate_iaq(
    gas_data: &mut VecDeque<u32>,
    last_iaq: &mut i32,
    gas_resistance: u32,
    humidity: f64,
) -> i32 {
    gas_data.pop_front();
    gas_data.push_back(gas_resistance);

    let sum: u64 = gas_data.iter().map(|&v| v as u64).sum();
    let gas_baseline = sum / GAS_BURN_IN as u64;
    if gas_baseline == 0 {
        return *last_iaq;
    }
    let gas_baseline = gas_baseline as f64;

    let gas_offset = gas_baseline - gas_resistance as f64;
    let hum_offset = humidity - HUMIDITY_BASELINE;

    let hum_score = if hum_offset > 0.0 {
        (100.0 - HUMIDITY_BASELINE - hum_offset)
            / (100.0 - HUMIDITY_BASELINE)
            * (HUMIDITY_WEIGHT * 100.0)
    } else {
        (HUMIDITY_BASELINE + hum_offset) / HUMIDITY_BASELINE
            * (HUMIDITY_WEIGHT * 100.0)
    };

    let gas_weight = 100.0 - (HUMIDITY_WEIGHT * 100.0);
    let gas_score = if gas_offset > 0.0 {
        (gas_resistance as f64 / gas_baseline) * gas_weight
    } else {
        gas_weight
    };

    *last_iaq = (hum_score + gas_score).round() as i32;
    *last_iaq
}

// -- SCD30 CRC-8 -------------------------------------------------------------

#[cfg(target_os = "linux")]
fn crc8(data: &[u8]) -> u8 {
    let mut crc: u8 = 0xFF;
    for &byte in data {
        crc ^= byte;
        for _ in 0..8 {
            if crc & 0x80 != 0 {
                crc = (crc << 1) ^ 0x31;
            } else {
                crc <<= 1;
            }
        }
    }
    crc
}

#[cfg(target_os = "linux")]
fn extract_float(bytes: &[u8]) -> Option<f32> {
    if crc8(&bytes[0..2]) != bytes[2]
        || crc8(&bytes[3..5]) != bytes[5]
    {
        return None;
    }
    let bits =
        u32::from_be_bytes([bytes[0], bytes[1], bytes[3], bytes[4]]);
    Some(f32::from_bits(bits))
}

// -- Rounding Helper ---------------------------------------------------------

#[cfg(target_os = "linux")]
fn round(value: f64, places: u32) -> f64 {
    let factor = 10_f64.powi(places as i32);
    (value * factor).round() / factor
}

// -- Linux Sensor Implementations --------------------------------------------

#[cfg(target_os = "linux")]
mod hw {
    use super::*;
    use bme680::{
        Bme680, I2CAddress, IIRFilterSize, OversamplingSetting,
        PowerMode, SettingsBuilder,
    };
    use embedded_hal::blocking::i2c::{Read, Write};
    use linux_embedded_hal::{Delay, I2cdev};
    use std::thread;
    use std::time::Duration;

    pub struct Bme680Sensor {
        dev: Bme680<I2cdev, Delay>,
        delay: Delay,
        gas_data: VecDeque<u32>,
        last_iaq: i32,
    }

    impl Bme680Sensor {
        pub fn new(i2c_bus: u8) -> Self {
            let i2c = I2cdev::new(format!("/dev/i2c-{i2c_bus}"))
                .expect("Failed to open I2C device");
            let mut delay = Delay;
            let mut dev =
                Bme680::init(i2c, &mut delay, I2CAddress::Primary)
                    .expect("Failed to init BME680");

            let settings = SettingsBuilder::new()
                .with_humidity_oversampling(
                    OversamplingSetting::OS2x,
                )
                .with_pressure_oversampling(
                    OversamplingSetting::OS4x,
                )
                .with_temperature_oversampling(
                    OversamplingSetting::OS8x,
                )
                .with_temperature_filter(IIRFilterSize::Size3)
                .with_gas_measurement(
                    Duration::from_millis(150),
                    320,
                    25,
                )
                .with_run_gas(true)
                .build();
            dev.set_sensor_settings(&mut delay, settings)
                .expect("Failed to configure BME680");

            Bme680Sensor {
                dev,
                delay,
                gas_data: VecDeque::from(vec![0u32; GAS_BURN_IN]),
                last_iaq: 0,
            }
        }
    }

    impl Sensor for Bme680Sensor {
        fn name(&self) -> &str {
            "BME680"
        }

        fn read(&mut self) -> Option<Value> {
            self.dev
                .set_sensor_mode(&mut self.delay, PowerMode::ForcedMode)
                .ok()?;
            thread::sleep(Duration::from_millis(200));

            let (data, _state) =
                self.dev.get_sensor_data(&mut self.delay).ok()?;

            let gas_resistance =
                data.gas_resistance_ohm();
            let humidity = data.humidity_percent() as f64;
            let iaq = calculate_iaq(
                &mut self.gas_data,
                &mut self.last_iaq,
                gas_resistance,
                humidity,
            );

            Some(json!({
                "temperature": round(data.temperature_celsius() as f64, 1),
                "humidity": round(humidity, 1),
                "pressure": round(data.pressure_hpa() as f64, 2),
                "iaq": iaq,
            }))
        }

        fn read_discovery(&mut self) -> Value {
            match self.read() {
                Some(v) => json!({
                    "temp": v["temperature"],
                    "hum": v["humidity"],
                    "press": v["pressure"],
                    "iaq": v["iaq"],
                }),
                None => json!({}),
            }
        }
    }

    pub struct Scd30Sensor {
        i2c: I2cdev,
    }

    const SCD30_ADDR: u8 = 0x61;

    impl Scd30Sensor {
        pub fn new(i2c_bus: u8) -> Self {
            let mut i2c = I2cdev::new(format!("/dev/i2c-{i2c_bus}"))
                .expect("Failed to open I2C device");

            // Set measurement interval to 2 seconds
            let arg: u16 = 2;
            let arg_bytes = arg.to_be_bytes();
            let crc = crc8(&arg_bytes);
            let cmd: u16 = 0x4600;
            let cmd_bytes = cmd.to_be_bytes();
            let buf = [
                cmd_bytes[0], cmd_bytes[1],
                arg_bytes[0], arg_bytes[1], crc,
            ];
            i2c.write(SCD30_ADDR, &buf)
                .expect("Failed to set measurement interval");
            thread::sleep(Duration::from_millis(30));

            // Start continuous measurement (ambient pressure 0 = default)
            let arg: u16 = 0;
            let arg_bytes = arg.to_be_bytes();
            let crc = crc8(&arg_bytes);
            let cmd: u16 = 0x0010;
            let cmd_bytes = cmd.to_be_bytes();
            let buf = [
                cmd_bytes[0], cmd_bytes[1],
                arg_bytes[0], arg_bytes[1], crc,
            ];
            i2c.write(SCD30_ADDR, &buf)
                .expect("Failed to start continuous measurement");
            thread::sleep(Duration::from_millis(30));

            Scd30Sensor { i2c }
        }

        fn data_ready(&mut self) -> bool {
            let cmd: u16 = 0x0202;
            let cmd_bytes = cmd.to_be_bytes();
            if self.i2c.write(SCD30_ADDR, &cmd_bytes).is_err() {
                return false;
            }
            thread::sleep(Duration::from_millis(30));

            let mut buf = [0u8; 3];
            if self.i2c.read(SCD30_ADDR, &mut buf).is_err() {
                return false;
            }
            let value = u16::from_be_bytes([buf[0], buf[1]]);
            value == 1
        }

        fn read_measurement(&mut self) -> Option<(f64, f64, f64)> {
            let cmd: u16 = 0x0300;
            let cmd_bytes = cmd.to_be_bytes();
            self.i2c.write(SCD30_ADDR, &cmd_bytes).ok()?;
            thread::sleep(Duration::from_millis(30));

            let mut buf = [0u8; 18];
            self.i2c.read(SCD30_ADDR, &mut buf).ok()?;

            let co2 = extract_float(&buf[0..6])? as f64;
            let temp = extract_float(&buf[6..12])? as f64;
            let hum = extract_float(&buf[12..18])? as f64;

            Some((co2, temp, hum))
        }
    }

    impl Sensor for Scd30Sensor {
        fn name(&self) -> &str {
            "SCD30"
        }

        fn read(&mut self) -> Option<Value> {
            if !self.data_ready() {
                return None;
            }
            let (co2, temp, hum) = self.read_measurement()?;
            Some(json!({
                "temperature": round(temp, 1),
                "humidity": round(hum, 1),
                "co2": round(co2, 1),
            }))
        }

        fn read_discovery(&mut self) -> Value {
            match self.read() {
                Some(v) => json!({
                    "temp": v["temperature"],
                    "hum": v["humidity"],
                    "co2": v["co2"],
                }),
                None => json!({}),
            }
        }
    }

    pub fn create_sensor(
        sensor_type: &str,
        i2c_bus: u8,
    ) -> Box<dyn Sensor> {
        match sensor_type {
            "BME680" => Box::new(Bme680Sensor::new(i2c_bus)),
            "SCD30" => Box::new(Scd30Sensor::new(i2c_bus)),
            _ => {
                eprintln!(
                    "Error: Unknown sensor type '{sensor_type}'."
                );
                eprintln!("Supported: BME680, SCD30");
                process::exit(1);
            }
        }
    }
}

// -- Stub Sensor (non-Linux) -------------------------------------------------

#[cfg(not(target_os = "linux"))]
mod hw {
    use super::*;

    struct StubSensor {
        sensor_name: String,
    }

    impl Sensor for StubSensor {
        fn name(&self) -> &str {
            &self.sensor_name
        }

        fn read(&mut self) -> Option<Value> {
            None
        }

        fn read_discovery(&mut self) -> Value {
            json!({})
        }
    }

    pub fn create_sensor(
        sensor_type: &str,
        _i2c_bus: u8,
    ) -> Box<dyn Sensor> {
        match sensor_type {
            "BME680" | "SCD30" => {}
            _ => {
                eprintln!(
                    "Error: Unknown sensor type '{sensor_type}'."
                );
                eprintln!("Supported: BME680, SCD30");
                process::exit(1);
            }
        }
        eprintln!(
            "Warning: I2C sensors only available on Linux. \
             Using stub sensor."
        );
        Box::new(StubSensor {
            sensor_name: sensor_type.to_string(),
        })
    }
}

// -- Shared State ------------------------------------------------------------

struct AppState {
    sensor: Mutex<Box<dyn Sensor>>,
    hostname: String,
    api_key: String,
}

// -- UDP Discovery -----------------------------------------------------------

async fn start_udp_discovery(state: Arc<AppState>) {
    let socket = UdpSocket::bind(("0.0.0.0", UDP_PORT))
        .await
        .expect("Failed to bind UDP socket");
    println!("UDP discovery listening on port {UDP_PORT}");

    let mut buf = [0u8; 1024];
    loop {
        let (len, addr) = match socket.recv_from(&mut buf).await {
            Ok(v) => v,
            Err(e) => {
                eprintln!("UDP recv error: {e}");
                continue;
            }
        };

        let msg = String::from_utf8_lossy(&buf[..len]);
        if msg.trim() != "DIASHOW_SCAN" {
            continue;
        }

        let ip = local_ip_address::local_ip()
            .map(|ip| ip.to_string())
            .unwrap_or_else(|_| "127.0.0.1".to_string());

        let response = {
            let mut sensor = state.sensor.lock().unwrap();
            let name = sensor.name().to_string();
            let discovery = sensor.read_discovery();
            let mut r = json!({
                "type": name,
                "host": &state.hostname,
                "ip": ip,
                "port": HTTPS_PORT,
            });
            if let (Some(resp), Some(disc)) =
                (r.as_object_mut(), discovery.as_object())
            {
                for (k, v) in disc {
                    resp.insert(k.clone(), v.clone());
                }
            }
            r
        };

        let payload = serde_json::to_vec(&response)
            .unwrap_or_default();
        let _ = socket.send_to(&payload, addr).await;
    }
}

// -- HTTPS REST API ----------------------------------------------------------

async fn sensor_handler(
    State(state): State<Arc<AppState>>,
    headers: HeaderMap,
) -> Result<Json<Value>, StatusCode> {
    let key = headers
        .get("X-Api-Key")
        .and_then(|v| v.to_str().ok())
        .unwrap_or("");
    if key != state.api_key {
        return Err(StatusCode::UNAUTHORIZED);
    }

    let mut sensor = state.sensor.lock().unwrap();
    let data = sensor.read();
    match data {
        Some(data) => {
            let name = sensor.name().to_string();
            drop(sensor);
            let mut response = json!({
                "sensor": name,
                "host": &state.hostname,
            });
            if let (Some(resp), Some(d)) =
                (response.as_object_mut(), data.as_object())
            {
                for (k, v) in d {
                    resp.insert(k.clone(), v.clone());
                }
            }
            Ok(Json(response))
        }
        None => Err(StatusCode::SERVICE_UNAVAILABLE),
    }
}

// -- Main --------------------------------------------------------------------

#[tokio::main]
async fn main() {
    println!("--- DiashowDL Sensor Node (Rust) ---");

    let config = load_config();
    let sensor_type = config.sensor.to_uppercase();
    let hostname = if config.hostname.is_empty() {
        hostname::get()
            .map(|h| h.to_string_lossy().to_string())
            .unwrap_or_else(|_| "unknown".to_string())
    } else {
        config.hostname.clone()
    };

    let sensor = hw::create_sensor(&sensor_type, config.i2c_bus);
    println!("Sensor: {sensor_type} on /dev/i2c-{}", config.i2c_bus);
    println!("Hostname: {hostname}");

    let state = Arc::new(AppState {
        sensor: Mutex::new(sensor),
        hostname,
        api_key: config.api_key.clone(),
    });

    // Spawn UDP discovery as background task
    let udp_state = state.clone();
    tokio::spawn(async move {
        start_udp_discovery(udp_state).await;
    });

    // Start HTTPS server
    let app = Router::new()
        .route("/", get(sensor_handler))
        .with_state(state);

    let tls_config = RustlsConfig::from_pem_file(
        &config.ssl_cert,
        &config.ssl_key,
    )
    .await
    .expect("Failed to load TLS certificates");

    let addr = SocketAddr::from(([0, 0, 0, 0], HTTPS_PORT));
    println!("HTTPS server on port {HTTPS_PORT}");

    axum_server::bind_rustls(addr, tls_config)
        .serve(app.into_make_service())
        .await
        .expect("HTTPS server failed");
}
