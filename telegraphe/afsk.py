"""Télégraphe — modem AFSK Bell 202 de référence (blueprint §8.2).

Mark 1200 Hz, space 2200 Hz, 1200 bauds, 22 050 Hz. Trame HDLC : fanions 0x7E, octets
émis bit de poids faible d'abord, bourrage d'un 0 après cinq 1, NRZI (un 0 change de ton,
un 1 le garde), FCS = CRC-16/X-25 émis octet faible d'abord. Démodulation par Goertzel,
synchronisation par essai de huit décalages dans la durée d'un bit.

Morse (1844), radio (1901) et Bell 202 (1976) sont anciens : la seule nouveauté revendiquée
par le projet est le sceau vérifiable par un témoin posé sur ce transport.

Ce module est la référence ; console/src/telegraphe.js en est le portage ligne à ligne,
et les deux sont vérifiés l'un contre l'autre (console/verifier.py).
"""

import math
import struct

FE, DEBIT = 22050, 1200
MARK, SPACE = 1200.0, 2200.0
FANION = (0, 1, 1, 1, 1, 1, 1, 0)
PREAMBULE, POSTAMBULE = 4, 2
AMPLITUDE = 0.8
ECH_PAR_BIT = FE / DEBIT


class ErreurTrame(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def crc16_x25(octets: bytes) -> int:
    crc = 0xFFFF
    for o in octets:
        crc ^= o
        for _ in range(8):
            crc = (crc >> 1) ^ 0x8408 if crc & 1 else crc >> 1
    return crc ^ 0xFFFF


def bits_trame(charge: bytes) -> list[int]:
    corps = charge + crc16_x25(charge).to_bytes(2, "little")
    bourres, uns = [], 0
    for octet in corps:
        for i in range(8):
            b = (octet >> i) & 1
            bourres.append(b)
            uns = uns + 1 if b else 0
            if uns == 5:
                bourres.append(0)
                uns = 0
    return list(FANION) * PREAMBULE + bourres + list(FANION) * POSTAMBULE


def moduler(charge: bytes) -> list[float]:
    echantillons, ton, phase = [], MARK, 0.0
    for i, bit in enumerate(bits_trame(charge)):
        if bit == 0:
            ton = SPACE if ton == MARK else MARK
        fin = math.floor((i + 1) * ECH_PAR_BIT + 0.5)
        while len(echantillons) < fin:
            echantillons.append(AMPLITUDE * math.sin(phase))
            phase += 2 * math.pi * ton / FE
    return echantillons


def goertzel(x, debut: int, fin: int, freq: float) -> float:
    c = 2 * math.cos(2 * math.pi * freq / FE)
    s1 = s2 = 0.0
    for n in range(debut, fin):
        s1, s2 = x[n] + c * s1 - s2, s1
    return s1 * s1 + s2 * s2 - c * s1 * s2


def _bits(x, decalage: float) -> list[int]:
    n = int((len(x) - decalage) / ECH_PAR_BIT)
    tons = []
    for i in range(n):
        a = math.floor(decalage + i * ECH_PAR_BIT + 0.5)
        b = math.floor(decalage + (i + 1) * ECH_PAR_BIT + 0.5)
        tons.append(goertzel(x, a, b, MARK) > goertzel(x, a, b, SPACE))
    return [1 if tons[i] == tons[i - 1] else 0 for i in range(1, n)]


def _detramer(bits: list[int]) -> tuple[bytes | None, bool]:
    """(charge valide ou None, une trame candidate a-t-elle été vue ?)"""
    fanions = [i for i in range(len(bits) - 7) if tuple(bits[i:i + 8]) == FANION]
    candidate = False
    for p, q in zip(fanions, fanions[1:]):
        brut, donnees, uns, valide = bits[p + 8:q], [], 0, True
        for b in brut:
            if uns == 5:
                uns = 0
                if b == 0:
                    continue            # bit de bourrage
                valide = False
                break
            donnees.append(b)
            uns = uns + 1 if b else 0
        if not valide or len(donnees) < 24 or len(donnees) % 8:
            continue
        candidate = True
        octets = bytes(sum(donnees[i + k] << k for k in range(8)) for i in range(0, len(donnees), 8))
        charge, fcs = octets[:-2], octets[-2] | octets[-1] << 8
        if crc16_x25(charge) == fcs:
            return charge, True
    return None, candidate


def demoduler(x) -> bytes:
    vue = False
    for k in range(8):
        charge, candidate = _detramer(_bits(x, k * ECH_PAR_BIT / 8))
        vue = vue or candidate
        if charge is not None:
            return charge
    raise ErreurTrame("crc_invalide" if vue else "aucune_trame")


def bruiter_bits(x, premier_bit: int, n_bits: int, graine: int = 42) -> None:
    """Corruption réaliste : remplace les échantillons de `n_bits` périodes par du bruit blanc.

    Plus destructrice qu'une simple inversion de ton (qui, à cause des 8 décalages de
    synchronisation testés, peut encore être démodulée avec un verdict CRC valide).
    """
    import random
    rng = random.Random(graine)
    a = math.floor(premier_bit * ECH_PAR_BIT + 0.5)
    b = math.floor((premier_bit + n_bits) * ECH_PAR_BIT + 0.5)
    for n in range(a, b):
        x[n] = rng.uniform(-AMPLITUDE, AMPLITUDE)


def vers_wav(x) -> bytes:
    pcm = b"".join(struct.pack("<h", max(-32768, min(32767, math.floor(v * 32767 + 0.5)))) for v in x)
    return (b"RIFF" + struct.pack("<I", 36 + len(pcm)) + b"WAVEfmt " +
            struct.pack("<IHHIIHH", 16, 1, 1, FE, FE * 2, 2, 16) + b"data" + struct.pack("<I", len(pcm)) + pcm)


def depuis_wav(octets: bytes) -> list[float]:
    if octets[:4] != b"RIFF" or octets[8:12] != b"WAVE":
        raise ErreurTrame("wav_invalide")
    fmt, canaux, fe, _, _, bits = struct.unpack("<HHIIHH", octets[20:36])
    if (fmt, canaux, fe, bits) != (1, 1, FE, 16) or octets[36:40] != b"data":
        raise ErreurTrame("wav_non_supporte")
    n = struct.unpack("<I", octets[40:44])[0] // 2
    return [v / 32767 for v in struct.unpack(f"<{n}h", octets[44:44 + 2 * n])]
