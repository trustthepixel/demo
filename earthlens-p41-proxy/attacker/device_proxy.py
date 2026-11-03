"""Attack proxy for TPX2 packets (runs on the Raspberry Pi).

The satellite uploads to this proxy; the proxy forwards to the ground station, optionally attacking
one packet. Controlled lab use: it only handles the team's own demonstration packets.

    python -m attacker.device_proxy --target http://<ground-station>:8000/ingest_v2 \
        --seed-file device_sat.seed.hex --port 8080

A menu appears in the terminal. An armed attack applies to the next packet only. The same menu
actions are available over HTTP: ``GET /__mode?m=tamper`` and ``GET /__status``.
"""
from __future__ import annotations

import argparse
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import requests
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from attacker.device_attacks import MODES, Attacker
from tp.device_protocol import HEADER_LEN, unpack_header

LABELS = {
    'passthrough': 'Normal: forward every packet unchanged',
    'tamper': 'D1  Edit the pixels in transit (next packet)',
    'stolen_key': 'D3  Forge a tile and sign it with the stolen satellite key (next packet)',
    'replay': 'D4  Send an old authentic packet again (next packet)',
    'drop': 'D7  Drop the next packet',
}
FAMILIES = ('inpaint_ns', 'cloud', 'copy_move', 'spectral', 'photometric', 'band_shift', 'compound')
SEVERITIES = ('subtle', 'medium', 'strong')


def _counter(packet):
    try:
        return unpack_header(packet[:HEADER_LEN])['counter']
    except (ValueError, KeyError):
        return '?'


def make_handler(attacker, lock, target, post=requests.post, log=print):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def _reply(self, code, body):
            data = body if isinstance(body, bytes) else json.dumps(body).encode()
            self.send_response(code)
            self.send_header('content-type', 'application/json')
            self.send_header('content-length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            parsed = urlsplit(self.path)
            if parsed.path == '/__status':
                self._reply(200, {'mode': attacker.mode, 'family': attacker.family, 'severity': attacker.severity})
            elif parsed.path == '/__mode':
                mode = parse_qs(parsed.query).get('m', [''])[0]
                try:
                    with lock:
                        attacker.arm(mode)
                    log(f'>>> armed: {LABELS[mode]}')
                    self._reply(200, {'mode': mode})
                except ValueError as exc:
                    self._reply(400, {'error': str(exc)})
            else:
                self._reply(404, {'error': 'not found'})

        def do_POST(self):
            body = self.rfile.read(int(self.headers.get('content-length') or 0))
            with lock:
                try:
                    actions = attacker.handle(body)
                except ValueError as exc:
                    log(f'!!! attack failed: {exc}')
                    actions = [('authentic', body)]
            if not actions:
                log(f'counter {_counter(body)} | dropped by the proxy')
                self._reply(200, {'status': 'dropped'})
                return
            response = None
            for label, packet in actions:
                try:
                    response = post(target, data=packet, headers={'content-type': 'application/octet-stream'}, timeout=60)
                    try:
                        verdict = response.json().get('status', 'unknown')
                    except ValueError:
                        verdict = 'invalid-response'
                    log(f'counter {_counter(packet)} | {label} | ground station says {verdict}')
                except requests.RequestException as exc:
                    log(f'counter {_counter(packet)} | {label} | ground station unreachable ({type(exc).__name__})')
                    self._reply(502, {'error': 'ground station unreachable'})
                    return
            self._reply(response.status_code, response.content)

    return Handler


def menu(attacker, lock, log=print, read=input):
    modes = list(MODES)
    while True:
        log('\n--- Attack menu ---')
        for index, mode in enumerate(modes):
            log(f'{index}. {LABELS[mode]}')
        log('f. Change attack family or severity')
        log('q. Quit')
        log(f'Current: mode={attacker.mode}, family={attacker.family}, severity={attacker.severity}')
        choice = read('Choose: ').strip().lower()
        if choice == 'q':
            return
        if choice == 'f':
            for index, name in enumerate(FAMILIES, 1):
                log(f'{index}. {name}')
            raw = read('Family number: ').strip()
            if raw.isdigit() and 1 <= int(raw) <= len(FAMILIES):
                attacker.family = FAMILIES[int(raw) - 1]
            raw = read('Severity 1=subtle 2=medium 3=strong: ').strip()
            if raw.isdigit() and 1 <= int(raw) <= 3:
                attacker.severity = SEVERITIES[int(raw) - 1]
            continue
        if choice.isdigit() and int(choice) < len(modes):
            try:
                with lock:
                    attacker.arm(modes[int(choice)])
                log(f'>>> armed: {LABELS[modes[int(choice)]]}')
            except ValueError as exc:
                log(f'Cannot arm: {exc}')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--target', required=True, help='ground station URL, for example http://192.168.1.10:8000/ingest_v2')
    parser.add_argument('--seed-file', type=Path, help='the stolen satellite seed (needed for the stolen-key attack)')
    parser.add_argument('--port', type=int, default=8080)
    args = parser.parse_args(argv)
    sk = None
    if args.seed_file:
        sk = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(args.seed_file.read_text(encoding='utf-8').strip()))
    attacker, lock = Attacker(sk), threading.Lock()
    server = ThreadingHTTPServer(('0.0.0.0', args.port), make_handler(attacker, lock, args.target))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    print(f'Proxy listening on port {args.port}, forwarding to {args.target}')
    try:
        menu(attacker, lock)
    except (KeyboardInterrupt, EOFError):
        pass
    server.shutdown()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
