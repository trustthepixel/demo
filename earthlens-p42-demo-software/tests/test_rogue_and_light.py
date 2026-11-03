import numpy as np

from attacker import rogue_sim
from scripts import verdict_light
from tp.chain import ChainedGround
from tp.device_protocol import DeviceGround, DeviceSource, parse_packet

META = {'lon': 10.18, 'lat': 36.8, 'date': '2026-05-01', 'tile': 'T32SNH', 'offset': 1000}


def _chip():
    return np.full((4, 256, 256), 1500, np.uint16)


def _ground():
    trusted = DeviceSource()
    return trusted, DeviceGround({trusted.key_id: trusted.public_key})


def test_rogue_own_key_is_rejected_as_unknown_signer():
    _, ground = _ground()
    result = ground.verify(parse_packet(rogue_sim.rogue_packet('own_key', _chip(), META)))
    assert result['provenance'] == 'INVALID' and 'unknown key' in ' '.join(result['reasons'])


def test_rogue_unsigned_has_unknown_provenance():
    _, ground = _ground()
    pkg = parse_packet(rogue_sim.rogue_packet('unsigned', _chip(), META))
    assert pkg['signature'] is None
    assert ground.verify(pkg)['provenance'] == 'UNKNOWN'


def test_rogue_run_posts_requested_count():
    sent = []

    class Reply:
        status_code = 200
        def json(self):
            return {'status': 'COMPROMISED', 'reasons': ['unknown key']}

    rows = [('chip_x', _chip(), META)]
    rogue_sim.run('http://x', 'own_key', 3, post=lambda url, data, **kw: sent.append(len(data)) or Reply(),
                  samples=rows, log=lambda *_: None)
    assert sent == [524473] * 3


def test_verdict_light_sends_one_character_per_new_event():
    events = [{'seq': 4, 'status': 'TRUSTED'}, {'seq': 5, 'status': 'SUSPICIOUS'}, {'seq': 6, 'status': 'COMPROMISED'}]

    class Reply:
        def __init__(self, rows): self.rows = rows
        def raise_for_status(self): pass
        def json(self): return {'events': self.rows}

    def get(url, params, timeout):
        return Reply([e for e in events if e['seq'] >= params['since']])

    assert verdict_light.latest_seq('http://x', get) == 6
    written = []
    since = verdict_light.poll_once('http://x', 5, written.append, get, log=lambda *_: None)
    assert written == ['S', 'C'] and since == 7
    assert verdict_light.poll_once('http://x', since, written.append, get, log=lambda *_: None) == 7 and written == ['S', 'C']
