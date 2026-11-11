"""Trame canal : la validité (correctness) est mathématique, pas électrique.

Format :  FLAG(0x7E) | LEN(2, big-endian) | PAYLOAD(LEN) | CRC-16/CCITT-FALSE(2)

Le CRC couvre LEN et PAYLOAD. Détecter une porteuse ou une tension de repos ne
prouve que la vivacité de la ligne ; seule une trame qui passe `decode` peut
être présentée à l'Invariant Gate.
"""

from binascii import crc_hqx

FLAG = 0x7E
MAX_PAYLOAD = 0xFFFF


class FrameError(ValueError):
    """Trame incomplète ou corrompue."""


def _crc(data: bytes) -> int:
    return crc_hqx(data, 0xFFFF)


def encode(payload: bytes) -> bytes:
    if len(payload) > MAX_PAYLOAD:
        raise FrameError(f"payload trop long : {len(payload)} > {MAX_PAYLOAD}")
    body = len(payload).to_bytes(2, "big") + payload
    return bytes([FLAG]) + body + _crc(body).to_bytes(2, "big")


def decode(frame: bytes) -> bytes:
    if len(frame) < 5:
        raise FrameError("trame tronquée")
    if frame[0] != FLAG:
        raise FrameError("fanion de synchronisation absent")
    length = int.from_bytes(frame[1:3], "big")
    if len(frame) != 5 + length:
        raise FrameError(f"longueur incohérente : annoncé {length}, reçu {len(frame) - 5}")
    body, crc = frame[1:-2], int.from_bytes(frame[-2:], "big")
    if _crc(body) != crc:
        raise FrameError("CRC invalide")
    return body[2:]
