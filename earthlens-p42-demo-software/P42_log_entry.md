### P42 - Demo software completed (rogue device, verdict light, runbook)

- Added `attacker/rogue_sim.py` (D2 own-key and D5 unsigned packets from Python) and `scripts/verdict_light.py`
  (polls `/events`, sends T, S or C to the Arduino; dry run without a port).
- Added firmware sketches `firmware/tpx2_rogue` (plain ESP32: BOOT press = D2, 1 s hold = D5) and
  `firmware/verdict_light` (Arduino Uno, LEDs on pins 8, 9, 10).
- Patched `firmware/tpx2_wifi_sat`: checked writes, full response printed, the counter advances only on a real verdict.
- D5 needs no endpoint change: an all-zero signature field is already read as a missing signature (SUSPICIOUS).
- Tests: `tests/test_rogue_and_light.py` (4 new, 15 in the demo test files, all passing). Sketches compiled on no board yet.
- Runbook: `reports/DEMO_RUNBOOK.md`.
