"""Verdict light bridge: forwards each new ground-station verdict to the Arduino as one character.

    python -m scripts.verdict_light --port COM10 --api http://127.0.0.1:8000

T = TRUSTED (green), S = SUSPICIOUS (yellow), C = COMPROMISED (red). Without ``--port`` it only prints
(dry run), which is useful to test the chain before the Arduino is connected. Needs ``pip install pyserial``
only when ``--port`` is used.
"""
from __future__ import annotations

import argparse
import time

import requests

CODES = {'TRUSTED': 'T', 'SUSPICIOUS': 'S', 'COMPROMISED': 'C'}


def fetch_events(api, since, get=requests.get):
    response = get(f'{api.rstrip("/")}/events', params={'since': since, 'limit': 1000}, timeout=10)
    response.raise_for_status()
    return response.json().get('events', [])


def latest_seq(api, get=requests.get):
    """Sequence number of the newest existing event (-1 when there is none), reading page by page."""
    since, newest = 0, -1
    while True:
        rows = fetch_events(api, since, get)
        if not rows:
            return newest
        newest = max(newest, max(int(r.get('seq', r.get('event_id', 0))) for r in rows))
        since = newest + 1


def poll_once(api, since, write, get=requests.get, log=print):
    """Send the character of every event newer than ``since``; return the new ``since``."""
    for row in fetch_events(api, since, get):
        seq = int(row.get('seq', row.get('event_id', 0)))
        status = row.get('status', '')
        code = CODES.get(status)
        if code:
            write(code)
        log(f'event {seq}: {status} -> {code or "?"}')
        since = max(since, seq + 1)
    return since


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--api', default='http://127.0.0.1:8000')
    parser.add_argument('--port', help='serial port of the Arduino, for example COM10; omit for a dry run')
    parser.add_argument('--baud', type=int, default=9600)
    parser.add_argument('--interval', type=float, default=0.5)
    args = parser.parse_args(argv)
    serial_port = None
    if args.port:
        import serial  # pyserial
        serial_port = serial.Serial(args.port, args.baud, timeout=1)
        time.sleep(2.0)  # the Arduino resets when the port opens
        write = lambda c: serial_port.write(c.encode('ascii'))
    else:
        write = lambda c: None
        print('Dry run: no serial port given, nothing is sent to an Arduino.')
    since = latest_seq(args.api) + 1
    print(f'Watching {args.api} from event {since}. Press Ctrl+C to stop.')
    try:
        while True:
            try:
                since = poll_once(args.api, since, write)
            except requests.RequestException as exc:
                print(f'ground station not reachable ({type(exc).__name__})')
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print('\nStopped.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
