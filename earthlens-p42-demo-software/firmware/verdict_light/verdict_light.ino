// Verdict light (Arduino Uno): one character over USB serial lights one LED.
//   T = TRUSTED (green, pin 8)   S = SUSPICIOUS (yellow, pin 9)   C = COMPROMISED (red, pin 10)
// Wiring: pin -> 220 ohm resistor -> LED long leg; LED short leg -> GND. Serial speed 9600.
const int GREEN = 8, YELLOW = 9, RED = 10;

void show(int pin) {
  digitalWrite(GREEN, pin == GREEN); digitalWrite(YELLOW, pin == YELLOW); digitalWrite(RED, pin == RED);
}

void setup() {
  pinMode(GREEN, OUTPUT); pinMode(YELLOW, OUTPUT); pinMode(RED, OUTPUT);
  Serial.begin(9600);
  int pins[3] = {GREEN, YELLOW, RED};          // start-up test: each LED in turn
  for (int i = 0; i < 3; i++) { show(pins[i]); delay(300); }
  show(-1);
}

void loop() {
  if (Serial.available()) {
    char c = Serial.read();
    if (c == 'T') show(GREEN);
    else if (c == 'S') show(YELLOW);
    else if (c == 'C') show(RED);
  }
}
