"""HTTP level test of the attack proxy against a small stand-in ground station."""
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import numpy as np
import requests

from attacker.device_attacks import Attacker
from attacker.device_proxy import make_handler
from tp.device_protocol import DeviceGround, DeviceSource, parse_packet

META = {'date': '2026-05-01', 'lon': 10.18, 'lat': 36.8, 'tile': 'T32SNH', 'offset': 1000}


def _chip(seed):
    return np.random.default_rng(seed).integers(1000, 3000, size=(4, 256, 256)).astype(np.uint16)


def _start(handler):
    server = ThreadingHTTPServer(('127.0.0.1', 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def _upstream(ground):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            body = self.rfile.read(int(self.headers['content-length']))
            result = ground.verify(parse_packet(body))
            bad = result['integrity'] == 'FAIL' or result['replay']
            status = 'COMPROMISED' if bad else 'SUSPICIOUS' if result['chain'] == 'GAP' else 'TRUSTED'
            data = json.dumps({'status': status}).encode()
            self.send_response(200)
            self.send_header('content-length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)
    return Handler


def test_proxy_forwards_attacks_once_and_reports_verdicts():
    source = DeviceSource()
    ground = DeviceGround({source.key_id: source.public_key})
    upstream = _start(_upstream(ground))
    attacker, lock, lines = Attacker(source._sk, seed=5), threading.Lock(), []
    proxy = _start(make_handler(attacker, lock, f'http://127.0.0.1:{upstream.server_port}/ingest_v2', log=lines.append))
    url = f'http://127.0.0.1:{proxy.server_port}'
    try:
        def send(seed):
            return requests.post(url + '/ingest_v2', data=source.acquire(_chip(seed), META), timeout=30).json()['status']

        assert send(0) == 'TRUSTED'
        assert requests.get(url + '/__mode?m=tamper', timeout=10).status_code == 200
        assert send(1) == 'COMPROMISED'
        assert requests.get(url + '/__status', timeout=10).json()['mode'] == 'passthrough'
        assert requests.get(url + '/__mode?m=drop', timeout=10).status_code == 200
        assert send(2) == 'dropped'
        assert send(3) == 'SUSPICIOUS'
        assert requests.get(url + '/__mode?m=nonsense', timeout=10).status_code == 400
        assert any('tampered' in line for line in lines)
    finally:
        proxy.shutdown()
        upstream.shutdown()


def test_proxy_reports_an_unreachable_ground_station():
    source = DeviceSource()
    proxy = _start(make_handler(Attacker(), threading.Lock(), 'http://127.0.0.1:9/ingest_v2', log=lambda _: None))
    try:
        reply = requests.post(f'http://127.0.0.1:{proxy.server_port}/ingest_v2', data=source.acquire(_chip(0), META), timeout=30)
        assert reply.status_code == 502
    finally:
        proxy.shutdown()
