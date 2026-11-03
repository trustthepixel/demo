// Rogue device (plain ESP32 DevKit): sends one hostile packet to the ground station.
//   short press on BOOT, or send 'a' on the serial monitor : D2, signed with its OWN key (unknown to the station)
//   hold BOOT for 1 second, or send 'b'                    : D5, unsigned (all-zero signature)
// Needs the "Crypto" library by Rhys Weatherley. Controlled lab use: it targets the team's own ground station.
#include <Arduino.h>
#include <WiFi.h>
#include <SHA256.h>
#include <Ed25519.h>

// ---- EDIT THESE LINES ----
const char* WIFI_SSID = "YOUR_WIFI_SSID";
const char* WIFI_PASS = "YOUR_WIFI_PASSWORD";
const char* HOST      = "172.20.10.7";   // ground station (the laptop)
// --------------------------
const uint16_t PORT = 8000;
const char* URL_PATH = "/ingest_v2";
const int BUTTON_PIN = 0;                // BOOT button
static const uint32_t PACKET_LEN = 121 + 64 + 524288;

static const uint8_t ROGUE_SEED[32] = {  // arbitrary key, deliberately NOT in trusted_keys
  0x42,0x42,0x42,0x42,0x42,0x42,0x42,0x42,0x42,0x42,0x42,0x42,0x42,0x42,0x42,0x42,
  0x42,0x42,0x42,0x42,0x42,0x42,0x42,0x42,0x42,0x42,0x42,0x42,0x42,0x42,0x42,0x42};
uint8_t pub[32], keyId[8];
uint32_t counter = 0;

static void put16(uint8_t* p, uint16_t v) { p[0] = v; p[1] = v >> 8; }
static void put32(uint8_t* p, uint32_t v) { for (int i = 0; i < 4; i++) p[i] = v >> (8 * i); }

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
static bool sendAll(WiFiClient& c, const uint8_t* p, size_t n) {
  size_t off = 0; uint32_t t0 = millis();
  while (off < n) {
    size_t w = c.write(p + off, n - off);
    if (w == 0) { if (!c.connected() || millis() - t0 > 10000) return false; delay(2); continue; }
    off += w; t0 = millis();
  }
  return true;
}

static void sendRogue(bool unsignedPacket) {
  counter++;
  uint8_t prev[32] = {0}, px[32]; pixelHash(counter - 1, px);
  uint8_t h[121] = {0}, nonce[8];
  for (int i = 0; i < 8; i++) nonce[i] = esp_random() & 0xFF;
  memcpy(h, "TPX2", 4); memcpy(h + 4, keyId, 8); put32(h + 12, counter);
  memcpy(h + 16, prev, 32); memcpy(h + 48, px, 32);
  put16(h + 80, 4); put16(h + 82, 256); put16(h + 84, 256); put16(h + 86, 1000);
  put32(h + 88, 10180000); put32(h + 92, 36800000); put32(h + 96, 20260501);
  memcpy(h + 100, nonce, 8); h[108] = 1; memcpy(h + 109, "T32SNH", 6);
  uint8_t head[185]; memcpy(head, h, 121);
  if (unsignedPacket) memset(head + 121, 0, 64);
  else Ed25519::sign(head + 121, ROGUE_SEED, pub, h, 121);

  WiFiClient client;
  if (!client.connect(HOST, PORT)) { Serial.println("cannot connect to the server"); return; }
  client.printf("POST %s HTTP/1.1\r\nHost: %s\r\nContent-Type: application/octet-stream\r\nContent-Length: %u\r\nConnection: close\r\n\r\n",
                URL_PATH, HOST, PACKET_LEN);
  bool ok = sendAll(client, head, 185);
  static uint8_t blk[2048];
  for (int c = 0; c < 4 && ok; c++) for (int y = 0; y < 256 && ok; y += 4) {
    for (int k = 0; k < 4; k++) fillRow(c, y + k, counter - 1, blk + 512 * k);
    ok = sendAll(client, blk, 2048);
  }
  if (!ok) { Serial.println("upload interrupted"); client.stop(); return; }
  uint32_t t0 = millis(); String resp;
  while ((client.connected() || client.available()) && millis() - t0 < 60000) {
    while (client.available()) resp += (char)client.read();
    delay(5);
  }
  int bs = resp.indexOf("\r\n\r\n");
  String body = bs >= 0 ? resp.substring(bs + 4) : resp;
  body.replace("\n", " ");
  Serial.printf("%s | %s\n", unsignedPacket ? "D5 unsigned" : "D2 own key", body.substring(0, 300).c_str());
}

void setup() {
  Serial.begin(115200); delay(1000);
  pinMode(BUTTON_PIN, INPUT_PULLUP);
  Ed25519::derivePublicKey(pub, ROGUE_SEED);
  SHA256 s; s.reset(); s.update(pub, 32); uint8_t d[32]; s.finalize(d, 32); memcpy(keyId, d, 8);
  WiFi.mode(WIFI_STA); WiFi.begin(WIFI_SSID, WIFI_PASS);
  Serial.print("joining Wi-Fi");
  while (WiFi.status() != WL_CONNECTED) { delay(500); Serial.print("."); }
  Serial.printf("\nconnected, address %s\nsend 'a' (own key) or 'b' (unsigned), or use the BOOT button\n", WiFi.localIP().toString().c_str());
}

void loop() {
  if (Serial.available()) {
    char c = Serial.read();
    if (c == 'a') sendRogue(false);
    if (c == 'b') sendRogue(true);
  }
  if (digitalRead(BUTTON_PIN) == LOW) {
    uint32_t t0 = millis();
    while (digitalRead(BUTTON_PIN) == LOW && millis() - t0 < 1000) delay(10);
    bool longPress = millis() - t0 >= 1000;
    while (digitalRead(BUTTON_PIN) == LOW) delay(10);
    sendRogue(longPress);
  }
}
