/*
 * DiashowDL ESP32 Digital Button Control
 *
 * Controls DiashowDL API via two buttons.
 * - Button 1 (Next)     -> /api/show/next
 * - Button 2 (Previous) -> /api/show/previous
 *
 * Required Libraries:
 * - WiFi
 * - HTTPClient
 */
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <HTTPClient.h>
#include "secrets.h"

// Hardware Pin Definitions (ESP32)
#define PIN_BTN_PREV 32
#define PIN_BTN_NEXT 33

// Debounce Configuration
#define DEBOUNCE_DELAY 300  // ms zwischen Triggers

// Zustandsvariablen für Debouncing (LOW = nicht gedrückt bei Pull-down)
bool lastStatePrev = LOW;
bool lastStateNext = LOW;
unsigned long lastPressPrev = 0;
unsigned long lastPressNext = 0;

void setup() {
    Serial.begin(115200);
    Serial.println("\n--- DiashowDL Button Controller ---");

    pinMode(PIN_BTN_PREV, INPUT_PULLUP);
    pinMode(PIN_BTN_NEXT, INPUT_PULLUP);

    WiFi.begin(WIFI_SSID, WIFI_PASS);
    Serial.print("Connecting to WiFi");
    while (WiFi.status() != WL_CONNECTED) {
        delay(500);
        Serial.print(".");
    }
    Serial.println("\nWiFi connected.");
    Serial.print("IP: ");
    Serial.println(WiFi.localIP());
}

void sendApiCommand(String endpoint) {
    if (WiFi.status() != WL_CONNECTED) {
        Serial.println("WiFi disconnected.");
        return;
    }

    WiFiClientSecure secureClient;
    secureClient.setInsecure();
    HTTPClient http;

    String url = "https://" + String(DIASHOW_IP) + ":" + String(DIASHOW_PORT) + endpoint;
    Serial.print("Sending command: ");
    Serial.println(endpoint);

    http.begin(secureClient, url);
    http.addHeader("X-Api-Key", DIASHOW_KEY);
    http.addHeader("Content-Type", "application/json");

    int httpCode = http.POST("{}");
    if (httpCode > 0) {
        Serial.print("Result: ");
        Serial.println(httpCode);
    } else {
        Serial.print("Error: ");
        Serial.println(http.errorToString(httpCode).c_str());
    }
    http.end();
}

void loop() {
    unsigned long now = millis();

    bool stateNext = digitalRead(PIN_BTN_NEXT);
    bool statePrev = digitalRead(PIN_BTN_PREV);

    // NEXT: steigende Flanke + Debounce
    if (stateNext == HIGH && lastStateNext == LOW) {
        if (now - lastPressNext > DEBOUNCE_DELAY) {
            Serial.println("Button Trigger: NEXT");
            sendApiCommand("/api/show/next");
            lastPressNext = now;
        }
    }
    lastStateNext = stateNext;

    // PREV: steigende Flanke + Debounce
    if (statePrev == HIGH && lastStatePrev == LOW) {
        if (now - lastPressPrev > DEBOUNCE_DELAY) {
            Serial.println("Button Trigger: PREV");
            sendApiCommand("/api/show/previous");
            lastPressPrev = now;
        }
    }
    lastStatePrev = statePrev;

    delay(20);
}