"""Rogue device stand-in: scenario D2 (own key) and D5 (unsigned) from a laptop or a Raspberry Pi.

The hardware rogue is a plain ESP32 (firmware/tpx2_rogue). This script sends the same two kinds of packet
from Python, so the scenarios can be tested without any board::

    python -m attacker.rogue_sim --url http://<ground-station>:8000/ingest_v2 --mode own_key
    python -m attacker.rogue_sim --url http://<ground-station>:8000/ingest_v2 --mode unsigned

Controlled lab use: it sends the team's own demonstration chips to the team's own ground station.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone

import requests

from attacker.device_feed import load_samples
from tp.device_protocol import HEADER_LEN, SIG_LEN, DeviceSource

MODES = ('own_key', 'unsigned')


def rogue_packet(mode, pixels, meta, source=None):
    """Return the bytes of one rogue packet. ``own_key`` is signed by a key nobody trusts; ``unsigned`` has an
    all-zero signature field, the wire representation of a missing signature."""
    if mode not in MODES:
        raise ValueError(f'unknown mode {mode}')
    data = (source or DeviceSource()).acquire(pixels, meta)
    if mode == 'unsigned':
        data = data[:HEADER_LEN] + bytes(SIG_LEN) + data[HEADER_LEN + SIG_LEN:]
    return data


def run(url, mode, count=1, post=requests.post, samples=None, log=print):
    rows = samples if samples is not None else load_samples()
    if not rows:
        raise ValueError('No sample chips found.')
    source = DeviceSource()  # one rogue identity for the whole run
    for index in range(count):
        name, pixels, meta = rows[index % len(rows)]
        data = rogue_packet(mode, pixels, meta, source)
        stamp = datetime.now(timezone.utc).isoformat(timespec='seconds')
        try:
            response = post(url, data=data, headers={'content-type': 'application/octet-stream'}, timeout=60)
            try:
                body = response.json()
                verdict = f"{body.get('status', 'unknown')} | {'; '.join(body.get('reasons', []))[:90]}"
            except ValueError:
                verdict = 'invalid-response'
            log(f'{stamp} | rogue {mode} | {name} | HTTP {response.status_code} | {verdict}')
        except requests.RequestException as exc:
            log(f'{stamp} | rogue {mode} | {name} | HTTP error ({type(exc).__name__})')
    return count


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--url', required=True)
    parser.add_argument('--mode', choices=MODES, required=True)
    parser.add_argument('--count', type=int, default=1)
    args = parser.parse_args(argv)
    run(args.url, args.mode, args.count)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
