"""TPX2 attacks, checked against the real ground-station verification (no model needed)."""
import numpy as np
import pytest

from attacker.device_attacks import Attacker, forge_packet, split_packet, tamper_packet
from tp.device_protocol import DeviceGround, DeviceSource, parse_packet

META = {'date': '2026-05-01', 'lon': 10.18, 'lat': 36.8, 'tile': 'T32SNH', 'offset': 1000}


def _chip(seed):
    rng = np.random.default_rng(seed)
    base = rng.integers(1000, 3000, size=(4, 256, 256))
    return base.astype(np.uint16)


def _setup():
    source = DeviceSource()
    ground = DeviceGround({source.key_id: source.public_key})
    return source, ground


def _verify(ground, data):
    return ground.verify(parse_packet(data))


def test_split_rejects_wrong_length():
    with pytest.raises(ValueError):
        split_packet(b'short')


def test_tamper_breaks_the_pixel_hash_but_not_the_signature():
    source, ground = _setup()
    result = _verify(ground, tamper_packet(source.acquire(_chip(0), META), rng=np.random.default_rng(1)))
    assert result['provenance'] == 'VALID' and result['integrity'] == 'FAIL'


def test_stolen_key_forgery_passes_signature_hash_and_chain():
    source, ground = _setup()
    _verify(ground, source.acquire(_chip(0), META))
    genuine = source.acquire(_chip(1), META)
    forged = forge_packet(genuine, source._sk, rng=np.random.default_rng(2))
    assert forged != genuine
    result = _verify(ground, forged)
    assert result['provenance'] == 'VALID' and result['integrity'] == 'PASS' and result['chain'] == 'OK'
    assert not np.array_equal(parse_packet(forged)['pixels'], parse_packet(genuine)['pixels'])


def test_genuine_packet_after_a_forgery_shows_a_chain_fork():
    source, ground = _setup()
    _verify(ground, source.acquire(_chip(0), META))
    _verify(ground, forge_packet(source.acquire(_chip(1), META), source._sk, rng=np.random.default_rng(3)))
    assert _verify(ground, source.acquire(_chip(2), META))['chain'] == 'FORK'


def test_forgery_with_the_wrong_seed_is_refused():
    source, _ = _setup()
    other = DeviceSource()
    with pytest.raises(ValueError):
        forge_packet(source.acquire(_chip(0), META), other._sk)


def test_attacker_is_one_shot_and_replay_is_caught():
    source, ground = _setup()
    attacker = Attacker(source._sk, seed=4)
    first = source.acquire(_chip(0), META)
    for label, packet in attacker.handle(first):
        _verify(ground, packet)
    attacker.arm('replay')
    actions = attacker.handle(source.acquire(_chip(1), META))
    assert [label for label, _ in actions] == ['replayed old packet', 'authentic']
    results = [_verify(ground, packet) for _, packet in actions]
    assert results[0]['replay'] is True and results[1]['replay'] is False
    assert attacker.mode == 'passthrough'


def test_replay_waits_until_a_previous_packet_exists():
    source, _ = _setup()
    attacker = Attacker(source._sk)
    attacker.arm('replay')
    assert [label for label, _ in attacker.handle(source.acquire(_chip(0), META))] == ['authentic']
    assert attacker.mode == 'replay'


def test_drop_removes_one_packet_and_creates_a_gap():
    source, ground = _setup()
    attacker = Attacker(source._sk)
    _verify(ground, attacker.handle(source.acquire(_chip(0), META))[0][1])
    attacker.arm('drop')
    assert attacker.handle(source.acquire(_chip(1), META)) == []
    assert _verify(ground, attacker.handle(source.acquire(_chip(2), META))[0][1])['chain'] == 'GAP'


def test_arming_stolen_key_without_a_seed_is_refused():
    with pytest.raises(ValueError):
        Attacker().arm('stolen_key')
    with pytest.raises(ValueError):
        Attacker().arm('nonsense')
