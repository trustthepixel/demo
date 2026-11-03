// ESP32-CAM satellite, step 4: builds a signed TPX2 packet and uploads it over Wi-Fi.
// Pixels are a synthetic test pattern for now (real tiles from the SD card come next).
// Needs the "Crypto" library and device_seed.h (made by scripts.make_device_key --c-header).
#include <Arduino.h>
#include <WiFi.h>
#include <Preferences.h>
#include <SHA256.h>
#include <Ed25519.h>
#include "device_seed.h"

// ---- EDIT THESE THREE LINES ----
const char* WIFI_SSID = "iPhone nada";
const char* WIFI_PASS = "nadou1234";
const char* HOST      = "172.20.10.7";   // laptop address (later: the Pi)
// --------------------------------
const uint16_t PORT = 8000;              // 8080 when going through the Pi proxy
const char* URL_PATH = "/ingest_v2";
const uint32_t INTERVAL_MS = 15000;

static const char* TILE = "T32SNH";
static const int32_t LON_E6 = 10180000, LAT_E6 = 36800000;
static const uint32_t DATE = 20260501;
static const uint32_t PACKET_LEN = 121 + 64 + 524288;

Preferences prefs;
uint8_t pub[32], keyId[8];

static void put16(uint8_t* p, uint16_t v) { p[0] = v; p[1] = v >> 8; }
static void put32(uint8_t* p, uint32_t v) { for (int i = 0; i < 4; i++) p[i] = v >> (8 * i); }
static int hexv(char c) { return c <= '9' ? c - '0' : (c | 32) - 'a' + 10; }

static void fillRow(int c, int y, uint32_t shift, uint8_t* row) {
  for (int x = 0; x < 256; x++) {
    uint16_t v = 1000 + ((c * 131 + y * 7 + x * 13 + shift) % 3000);
    row[2 * x] = v & 0xFF; row[2 * x + 1] = v >> 8;
  }
}

static void pixelHash(uint32_t shift, uint8_t* out) {
  SHA256 sha; sha.reset();
  uint8_t row[512];
  for (int c = 0; c < 4; c++) for (int y = 0; y < 256; y++) { fillRow(c, y, shift, row); sha.update(row, 512); }
  sha.finalize(out, 32);
}

static bool sendOne() {
  uint32_t counter = prefs.getUInt("ctr", 0) + 1;
  uint8_t prev[32] = {0};
  if (prefs.getBytesLength("prev") == 32) prefs.getBytes("prev", prev, 32);

  uint8_t px[32]; pixelHash(counter - 1, px);
  uint8_t h[121] = {0}, nonce[8];
  for (int i = 0; i < 8; i++) nonce[i] = esp_random() & 0xFF;
  memcpy(h, "TPX2", 4); memcpy(h + 4, keyId, 8); put32(h + 12, counter);
  memcpy(h + 16, prev, 32); memcpy(h + 48, px, 32);
  put16(h + 80, 4); put16(h + 82, 256); put16(h + 84, 256); put16(h + 86, 1000);
  put32(h + 88, LON_E6); put32(h + 92, LAT_E6); put32(h + 96, DATE);
  memcpy(h + 100, nonce, 8); h[108] = 1; memcpy(h + 109, TILE, strlen(TILE));
  uint8_t sig[64]; Ed25519::sign(sig, TP_SEED, pub, h, 121);

  WiFiClient client;
  if (!client.connect(HOST, PORT)) { Serial.println("cannot connect to the server"); return false; }
  client.printf("POST %s HTTP/1.1\r\nHost: %s\r\nContent-Type: application/octet-stream\r\nContent-Length: %u\r\nConnection: close\r\n\r\n",
                URL_PATH, HOST, PACKET_LEN);
  client.write(h, 121); client.write(sig, 64);
  uint8_t row[512];
  for (int c = 0; c < 4; c++) for (int y = 0; y < 256; y++) { fillRow(c, y, counter - 1, row); client.write(row, 512); }

  uint32_t t0 = millis();
  String status = client.readStringUntil('\n');
  String body;
  while (client.connected() && millis() - t0 < 60000) { while (client.available()) body += (char)client.read(); delay(5); }
  status.trim();
  Serial.printf("counter %u | %s | %s\n", counter, status.c_str(), body.substring(0, 160).c_str());

  if (status.indexOf(" 200") < 0) return false;   // only advance when the server really answered
  uint8_t buf[185], link[32];
  memcpy(buf, h, 121); memcpy(buf + 121, sig, 64);
  SHA256 s2; s2.reset(); s2.update(buf, 185); s2.finalize(link, 32);
  prefs.putUInt("ctr", counter); prefs.putBytes("prev", link, 32);
  return true;
}

void setup() {
  Serial.begin(115200); delay(1500);
  Ed25519::derivePublicKey(pub, TP_SEED);
  for (int i = 0; i < 8; i++) keyId[i] = hexv(TP_KEY_ID_HEX[2 * i]) * 16 + hexv(TP_KEY_ID_HEX[2 * i + 1]);
  prefs.begin("tpx2", false);
  Serial.printf("key id %s, last counter %u\n", TP_KEY_ID_HEX, prefs.getUInt("ctr", 0));
  WiFi.mode(WIFI_STA); WiFi.begin(WIFI_SSID, WIFI_PASS);
  Serial.print("joining Wi-Fi");
  while (WiFi.status() != WL_CONNECTED) { delay(500); Serial.print("."); }
  Serial.printf("\nconnected, my address %s\n", WiFi.localIP().toString().c_str());
}

void loop() {
  sendOne();
  delay(INTERVAL_MS);
}
