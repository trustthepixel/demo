# Demo runbook (at the bench)

Order matters: ground station first, then the light, then the senders. Replace `PY` with the full path of
the Python of your virtual environment. Laptop address on the hotspot: `172.20.10.7` (check with `ipconfig`).

| # | Where | Command or action | Expect |
|---|---|---|---|
| 1 | Laptop, window 1 | `PY -m uvicorn api:app --host 0.0.0.0 --port 8000` | `Uvicorn running on http://0.0.0.0:8000` |
| 2 | Laptop, window 2 | `curl.exe -s http://127.0.0.1:8000/health` | `"ok":true`, the esp32cam key id in the list |
| 3 | Laptop, window 3 | `PY -m scripts.verdict_light --port COM_ARDUINO` (no `--port` for a dry run) | `Watching ... from event N` |
| 4 | Pi | `python -m attacker.device_proxy --target http://172.20.10.7:8000/ingest_v2 --seed-file device_sat.seed.hex --port 8080` | `Proxy listening on port 8080` |
| 5 | Pi, second SSH | `python -m attacker.device_feed --url http://127.0.0.1:8080/ingest_v2 --seed-file device_sat.seed.hex --interval 5 --count 3` | TRUSTED (or SUSPICIOUS on a chip the model dislikes) |

Attacks (Pi, any time before a feed run): `curl "http://127.0.0.1:8080/__mode?m=MODE"` with MODE =
`tamper` (D1), `stolen_key` (D3), `replay` (D4), `drop` (D7). Each applies to the next packet only.

Rogue (D2, D5): press BOOT on the ESP32 DevKit (D2, own key), hold it for 1 second (D5, unsigned), or send
`a` / `b` on its serial monitor. Without the board: `PY -m attacker.rogue_sim --url http://172.20.10.7:8000/ingest_v2 --mode own_key`
(or `--mode unsigned`).

Satellite board (ESP32-CAM): restart the API first, then power the board; `RESET_CHAIN = true` makes it start
again at counter 1.

Expected verdicts: D0 TRUSTED, D1 COMPROMISED, D2 COMPROMISED, D3 COMPROMISED then COMPROMISED (chain fork),
D4 COMPROMISED, D5 SUSPICIOUS, D7 SUSPICIOUS then TRUSTED. D5 needs no endpoint change: an all-zero
signature field is read as a missing signature.

Light: green TRUSTED, yellow SUSPICIOUS, red COMPROMISED (Arduino pins 8, 9, 10, each LED through 220 ohm to GND).
