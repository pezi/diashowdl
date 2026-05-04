/*
 * DiashowDL ESP32 Grove Gesture Control
 * 
 * Maps Grove Gesture v1.0 (PAJ7620U2) swipes to DiashowDL API commands.
 * - Swipe Left  -> Previous Slide
 * - Swipe Right -> Next Slide
 * 
 * Required Libraries:
 * - Seeed_Arduino_PAJ7620 (by Seeed Studio)
 * - WiFi
 * - HTTPClient
 */

#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <HTTPClient.h>
#include <Wire.h>
#include "paj7620.h"
#include "secrets.h"

// Constants
#define GESTURE_COOLDOWN 800  // ms between commands

unsigned long lastGestureTime = 0;

void setup() {
    Serial.begin(115200);
    Serial.println("\n--- DiashowDL Gesture Controller ---");

    // 1. Initialize Sensor
    if (paj7620Init()) {
        Serial.println("Error: Gesture sensor (PAJ7620) not found!");
        while (1);
    }
    Serial.println("Gesture sensor initialized.");
    

    // 2. Connect WiFi
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
        Serial.println("WiFi disconnected. Reconnecting...");
        return;
    }

    WiFiClientSecure secureClient;
    secureClient.setInsecure();

    HTTPClient http;
    String url = "https://" + String(DIASHOW_IP) + ":" + String(DIASHOW_PORT) + endpoint;

    Serial.print("Sending command to: ");
    Serial.println(url);

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
    uint8_t data = 0;
    paj7620ReadReg(0x43, 1, &data);

    if (data && (millis() - lastGestureTime > GESTURE_COOLDOWN)) {
        switch (data) {
            case GES_RIGHT_FLAG:
                Serial.println("Gesture: RIGHT -> Next Slide");
                sendApiCommand("/api/show/next");
                lastGestureTime = millis();
                break;

            case GES_LEFT_FLAG:
                Serial.println("Gesture: LEFT -> Previous Slide");
                sendApiCommand("/api/show/previous");
                lastGestureTime = millis();
                break;


            default:
                // Ignore other gestures (down, clockwise, etc.)
                break;
        }
    }
    delay(50);
}
