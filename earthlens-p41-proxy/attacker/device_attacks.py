"""Attacks on TPX2 packets, used by the Raspberry Pi attack proxy.

Controlled lab use only: these functions edit packets of the team's own demonstration source and
need no access to any real system. Each function takes the raw packet bytes and returns new bytes.
"""
from __future__ import annotations

import hashlib
import os

import numpy as np
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from tp import attacks
from tp.device_protocol import HEADER_LEN, PACKET_LEN, SHAPE, SIG_LEN, key_id_bytes, pack_header, unpack_header

MODES = ('passthrough', 'tamper', 'stolen_key', 'replay', 'drop')


def split_packet(data):
    """Return ``(header, signature, pixels)`` of a TPX2 packet. Raises ValueError on a wrong length."""
    if len(data) != PACKET_LEN:
        raise ValueError(f'wrong packet length {len(data)}')
    pixels = np.frombuffer(data, dtype='<u2', offset=HEADER_LEN + SIG_LEN).astype(np.uint16).reshape(SHAPE)
    return data[:HEADER_LEN], data[HEADER_LEN:HEADER_LEN + SIG_LEN], pixels


def _edit(pixels, offset, family, severity, rng):
    donor = pixels[:, ::-1, ::-1].copy()
    edited, _, _ = attacks.make_attack(pixels, donor, family, severity, rng, offset)
    return np.ascontiguousarray(edited, dtype='<u2').tobytes()


def tamper_packet(data, family='inpaint_ns', severity='strong', rng=None):
    """Edit the pixels and keep the signed header: the pixel hash no longer matches."""
    header, signature, pixels = split_packet(data)
    offset = unpack_header(header)['offset']
    rng = rng if rng is not None else np.random.default_rng()
    return header + signature + _edit(pixels, offset, family, severity, rng)


def forge_packet(data, sk: Ed25519PrivateKey, family='inpaint_ns', severity='strong', rng=None):
    """Replace the pixels and sign again with ``sk`` (the stolen key), keeping counter and chain link."""
    header, _, pixels = split_packet(data)
    fields = unpack_header(header)
    if key_id_bytes(sk.public_key()).hex() != fields['key_id']:
        raise ValueError('the seed does not belong to the key that signed this packet')
    rng = rng if rng is not None else np.random.default_rng()
    new_pixels = _edit(pixels, fields['offset'], family, severity, rng)
    new_header = pack_header(
        bytes.fromhex(fields['key_id']), fields['counter'], fields['prev_hash'], hashlib.sha256(new_pixels).hexdigest(),
        fields['offset'], fields['geo'][0], fields['geo'][1], fields['time_utc'], os.urandom(8), fields['tile'],
        tuple(fields['window']), fields['sensor_code'], tuple(fields['shape']))
    return new_header + sk.sign(new_header) + new_pixels


class Attacker:
    """One-shot attack state: an armed mode applies to the next packet, then the proxy goes back to normal."""

    def __init__(self, sk=None, family='inpaint_ns', severity='strong', seed=None):
        self.sk = sk
        self.family = family
        self.severity = severity
        self.mode = 'passthrough'
        self.last = None  # last authentic packet that went through untouched
        self.rng = np.random.default_rng(seed)

    def arm(self, mode):
        if mode not in MODES:
            raise ValueError(f'unknown mode {mode}')
        if mode == 'stolen_key' and self.sk is None:
            raise ValueError('no stolen seed was given')
        self.mode = mode

    def handle(self, data):
        """Return the packets to send upstream, in order, as ``(label, bytes)``. An empty list means dropped."""
        mode = self.mode
        try:
            split_packet(data)
        except ValueError:
            return [('authentic', data)]
        if mode == 'drop':
            self.mode = 'passthrough'
            return []
        if mode == 'tamper':
            self.mode = 'passthrough'
            return [('tampered', tamper_packet(data, self.family, self.severity, self.rng))]
        if mode == 'stolen_key':
            self.mode = 'passthrough'
            return [('forged with stolen key', forge_packet(data, self.sk, self.family, self.severity, self.rng))]
        out = []
        if mode == 'replay' and self.last is not None:
            out.append(('replayed old packet', self.last))
            self.mode = 'passthrough'
        out.append(('authentic', data))
        self.last = data
        return out
