/*
 * DiashowDL Sensor Node — ESP32
 *
 * Implements the DiashowDL Sensor Interface (see docs/sensor.md).
 * Supports BME680 (IAQ) or SCD30 (CO2) via I2C.
 *
 * - HTTPS REST API on port 9132 (self-signed cert generated at boot)
 * - UDP Discovery on port 9133
 *
 * Required Libraries:
 *   ArduinoJson, WiFi, WiFiUdp, Wire
 *   Adafruit BME680 Library (for BME680) or SparkFun_SCD30 (for SCD30)
 */

#include <WiFi.h>
#include <WiFiUdp.h>
#include <ArduinoJson.h>
#include <Wire.h>
#include "secrets.h"

// mbedTLS for HTTPS server
#include "mbedtls/ssl.h"
#include "mbedtls/pk.h"
#include "mbedtls/x509_crt.h"
#include "mbedtls/entropy.h"
#include "mbedtls/ctr_drbg.h"
#include "mbedtls/net_sockets.h"
#include "mbedtls/error.h"

// --- Sensor Selection (change this line) ---
#define SENSOR_BME680 0
#define SENSOR_SCD30  1
#define ACTIVE_SENSOR SENSOR_BME680

// --- Sensor Libraries ---
#if ACTIVE_SENSOR == SENSOR_BME680
  #include <Adafruit_BME680.h>
  Adafruit_BME680 bme;
  const char* SENSOR_NAME = "BME680";
#else
  #include <SparkFun_SCD30_Arduino_Library.h>
  SCD30 scd30;
  const char* SENSOR_NAME = "SCD30";
#endif

// --- Network Ports ---
const int HTTPS_PORT = 9132;
const int UDP_PORT   = 9133;

WiFiUDP udp;
WiFiServer tcpServer(HTTPS_PORT);

// --- mbedTLS contexts ---
mbedtls_ssl_config sslConf;
mbedtls_x509_crt srvcert;
mbedtls_pk_context pkey;
mbedtls_entropy_context entropy;
mbedtls_ctr_drbg_context ctr_drbg;

// --- IAQ Calculation (ported from dart_periphery BME680 driver) ---
#if ACTIVE_SENSOR == SENSOR_BME680
const int GAS_BURN_IN       = 50;
const float HUM_BASELINE    = 40.0;
const float HUM_WEIGHT      = 0.25;

int gasData[GAS_BURN_IN];
int gasDataIndex = 0;
int lastIaq      = 0;
#endif

// --- Forward Declarations ---
void handleUdpDiscovery();
void handleTlsClient();
String buildSensorJson(bool shortKeys);
#if ACTIVE_SENSOR == SENSOR_BME680
int calculateIaq(int gasResistance, float humidity);
#endif

// ============================================================
void setup() {
  Serial.begin(115200);
  Serial.println("\n--- DiashowDL Sensor Node ---");

  Wire.begin();

  // Initialize sensor
#if ACTIVE_SENSOR == SENSOR_BME680
  if (!bme.begin(0x76)) {
    Serial.println("Error: BME680 not found!");
    while (1) delay(1000);
  }
  bme.setTemperatureOversampling(BME680_OS_8X);
  bme.setHumidityOversampling(BME680_OS_2X);
  bme.setPressureOversampling(BME680_OS_4X);
  bme.setIIRFilterSize(BME680_FILTER_SIZE_3);
  bme.setGasHeater(320, 150);
  memset(gasData, 0, sizeof(gasData));
#else
  if (!scd30.begin()) {
    Serial.println("Error: SCD30 not found!");
    while (1) delay(1000);
  }
#endif

  // Connect WiFi
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  Serial.print("Connecting to WiFi");
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("\nWiFi connected.");
  Serial.print("IP: ");
  Serial.println(WiFi.localIP());

  // Initialize mbedTLS
  mbedtls_ssl_config_init(&sslConf);
  mbedtls_x509_crt_init(&srvcert);
  mbedtls_pk_init(&pkey);
  mbedtls_entropy_init(&entropy);
  mbedtls_ctr_drbg_init(&ctr_drbg);

  mbedtls_ctr_drbg_seed(&ctr_drbg, mbedtls_entropy_func, &entropy, NULL, 0);
  mbedtls_x509_crt_parse(&srvcert, (const unsigned char*)SERVER_CERT, strlen(SERVER_CERT) + 1);
  mbedtls_pk_parse_key(&pkey, (const unsigned char*)SERVER_KEY, strlen(SERVER_KEY) + 1, NULL, 0, mbedtls_ctr_drbg_random, &ctr_drbg);

  mbedtls_ssl_config_defaults(&sslConf, MBEDTLS_SSL_IS_SERVER,
    MBEDTLS_SSL_TRANSPORT_STREAM, MBEDTLS_SSL_PRESET_DEFAULT);
  mbedtls_ssl_conf_rng(&sslConf, mbedtls_ctr_drbg_random, &ctr_drbg);
  mbedtls_ssl_conf_own_cert(&sslConf, &srvcert, &pkey);

  // Start TCP server (TLS handshake per client)
  tcpServer.begin();

  // Start UDP listener
  udp.begin(UDP_PORT);

  Serial.print("Sensor: ");
  Serial.println(SENSOR_NAME);
  Serial.println("HTTPS on port 9132, UDP on port 9133");
}

// ============================================================
void loop() {
  handleUdpDiscovery();
  handleTlsClient();
  delay(1);
}

// ============================================================
// UDP Discovery — respond to DIASHOW_SCAN broadcasts
// ============================================================
void handleUdpDiscovery() {
  int packetSize = udp.parsePacket();
  if (!packetSize) return;

  char buffer[64];
  int len = udp.read(buffer, sizeof(buffer) - 1);
  buffer[len] = '\0';

  if (strstr(buffer, "DIASHOW_SCAN") == NULL) return;

  String json = buildSensorJson(true);
  udp.beginPacket(udp.remoteIP(), udp.remotePort());
  udp.print(json);
  udp.endPacket();
}

// ============================================================
// mbedTLS send/recv callbacks using WiFiClient fd
// ============================================================
static int tlsSend(void* ctx, const unsigned char* buf, size_t len) {
  WiFiClient* client = (WiFiClient*)ctx;
  return client->write(buf, len);
}

static int tlsRecv(void* ctx, unsigned char* buf, size_t len) {
  WiFiClient* client = (WiFiClient*)ctx;
  unsigned long start = millis();
  while (!client->available() && millis() - start < 3000) {
    delay(1);
  }
  if (!client->available()) return MBEDTLS_ERR_SSL_WANT_READ;
  return client->read(buf, len);
}

// ============================================================
// HTTPS handler — accept TCP, do TLS handshake, serve JSON
// ============================================================
void handleTlsClient() {
  WiFiClient client = tcpServer.accept();
  if (!client) return;

  mbedtls_ssl_context ssl;
  mbedtls_ssl_init(&ssl);
  mbedtls_ssl_setup(&ssl, &sslConf);
  mbedtls_ssl_set_bio(&ssl, &client, tlsSend, tlsRecv, NULL);

  // TLS handshake
  int ret;
  do {
    ret = mbedtls_ssl_handshake(&ssl);
  } while (ret == MBEDTLS_ERR_SSL_WANT_READ || ret == MBEDTLS_ERR_SSL_WANT_WRITE);

  if (ret != 0) {
    char errBuf[100];
    mbedtls_strerror(ret, errBuf, sizeof(errBuf));
    Serial.printf("TLS handshake failed: %s\n", errBuf);
    mbedtls_ssl_free(&ssl);
    client.stop();
    return;
  }

  // Read HTTP request
  char reqBuf[1024];
  int reqLen = 0;
  do {
    ret = mbedtls_ssl_read(&ssl, (unsigned char*)reqBuf + reqLen, sizeof(reqBuf) - reqLen - 1);
  } while (ret == MBEDTLS_ERR_SSL_WANT_READ);

  if (ret > 0) reqLen = ret;
  reqBuf[reqLen] = '\0';

  String headers(reqBuf);

  // Extract X-Api-Key
  String apiKey = "";
  int keyIdx = headers.indexOf("X-Api-Key:");
  if (keyIdx == -1) keyIdx = headers.indexOf("x-api-key:");
  if (keyIdx >= 0) {
    int valStart = keyIdx + 10;
    int valEnd = headers.indexOf('\n', valStart);
    if (valEnd == -1) valEnd = headers.length();
    apiKey = headers.substring(valStart, valEnd);
    apiKey.trim();
  }

  String response;
  if (apiKey != String(API_KEY)) {
    response = "HTTP/1.1 401 Unauthorized\r\nConnection: close\r\n\r\n";
  } else {
    String json = buildSensorJson(false);
    response = "HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nConnection: close\r\n\r\n" + json;
  }

  mbedtls_ssl_write(&ssl, (const unsigned char*)response.c_str(), response.length());
  mbedtls_ssl_close_notify(&ssl);
  mbedtls_ssl_free(&ssl);
  client.stop();
}

// ============================================================
// Build sensor JSON
// ============================================================
String buildSensorJson(bool shortKeys) {
  StaticJsonDocument<512> doc;

  if (shortKeys) {
    doc["type"] = SENSOR_NAME;
    doc["host"] = HOSTNAME;
    doc["ip"]   = WiFi.localIP().toString();
    doc["port"] = HTTPS_PORT;
  } else {
    doc["sensor"] = SENSOR_NAME;
    doc["host"]   = HOSTNAME;
  }

#if ACTIVE_SENSOR == SENSOR_BME680
  if (bme.performReading()) {
    if (shortKeys) {
      doc["temp"]  = bme.temperature;
      doc["hum"]   = bme.humidity;
      doc["press"] = bme.pressure / 100.0;
      doc["iaq"]   = calculateIaq((int)bme.gas_resistance, bme.humidity);
    } else {
      doc["temperature"] = bme.temperature;
      doc["humidity"]    = bme.humidity;
      doc["pressure"]    = bme.pressure / 100.0;
      doc["iaq"]         = calculateIaq((int)bme.gas_resistance, bme.humidity);
    }
  }
#else
  if (scd30.dataAvailable()) {
    if (shortKeys) {
      doc["temp"] = scd30.getTemperature();
      doc["hum"]  = scd30.getHumidity();
      doc["co2"]  = scd30.getCO2();
    } else {
      doc["temperature"] = scd30.getTemperature();
      doc["humidity"]    = scd30.getHumidity();
      doc["co2"]         = (double)scd30.getCO2();
    }
  }
#endif

  String output;
  serializeJson(doc, output);
  return output;
}

// ============================================================
// IAQ — rolling-baseline algorithm (ported from dart_periphery)
// ============================================================
#if ACTIVE_SENSOR == SENSOR_BME680
int calculateIaq(int gasResistance, float humidity) {
  gasData[gasDataIndex] = gasResistance;
  gasDataIndex = (gasDataIndex + 1) % GAS_BURN_IN;

  long sum = 0;
  for (int i = 0; i < GAS_BURN_IN; i++) sum += gasData[i];
  int gasBaseline = (int)round((double)sum / GAS_BURN_IN);
  if (gasBaseline == 0) { lastIaq = 0; return lastIaq; }

  int gasOffset   = gasBaseline - gasResistance;
  float humOffset = humidity - HUM_BASELINE;

  float humScore;
  if (humOffset > 0) {
    humScore = (100.0 - HUM_BASELINE - humOffset)
               / (100.0 - HUM_BASELINE)
               * (HUM_WEIGHT * 100.0);
  } else {
    humScore = (HUM_BASELINE + humOffset)
               / HUM_BASELINE
               * (HUM_WEIGHT * 100.0);
  }

  float gasWeight = 100.0 - (HUM_WEIGHT * 100.0);
  float gasScore;
  if (gasOffset > 0) {
    gasScore = ((float)gasResistance / gasBaseline) * gasWeight;
  } else {
    gasScore = gasWeight;
  }

  lastIaq = (int)round(humScore + gasScore);
  return lastIaq;
}
#endif
