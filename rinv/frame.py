"""Trame canal : la validité (correctness) est mathématique, pas électrique.

Format :  FLAG(0x7E) | LEN(2, gros-boutiste) | PAYLOAD(LEN) | FCS(2, petit-boutiste)

FCS = CRC-16/X-25 (poly 0x1021 réfléchi, init 0xFFFF, xorout 0xFFFF), le CRC
qu'impose le blueprint au télégraphe (§8.2), émis octet faible d'abord comme en
HDLC. Il couvre LEN et PAYLOAD. Cette trame n'est pas une trame HDLC complète :
pas de fanion de fin ni de bourrage de bits.

Détecter une porteuse ou une tension de repos ne prouve que la vivacité de la
ligne ; seule une trame qui passe `decode` peut être présentée à l'Invariant Gate.
"""

FLAG = 0x7E
MAX_PAYLOAD = 0xFFFF


def _table() -> list[int]:
    table = []
    for octet in range(256):
        crc = octet
        for _ in range(8):
            crc = (crc >> 1) ^ 0x8408 if crc & 1 else crc >> 1
        table.append(crc)
    return table


_TABLE = _table()


class FrameError(ValueError):
    """Trame incomplète ou corrompue. `code` est un identifiant stable."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _crc(data: bytes) -> int:
    crc = 0xFFFF
    for octet in data:
        crc = (crc >> 8) ^ _TABLE[(crc ^ octet) & 0xFF]
    return crc ^ 0xFFFF


def encode(payload: bytes) -> bytes:
    if len(payload) > MAX_PAYLOAD:
        raise FrameError("payload_trop_long", f"payload trop long : {len(payload)} > {MAX_PAYLOAD}")
    body = len(payload).to_bytes(2, "big") + payload
    return bytes([FLAG]) + body + _crc(body).to_bytes(2, "little")


def decode(frame: bytes) -> bytes:
    if len(frame) < 5:
        raise FrameError("trame_tronquee", "trame tronquée")
    if frame[0] != FLAG:
        raise FrameError("fanion_absent", "fanion de synchronisation absent")
    length = int.from_bytes(frame[1:3], "big")
    if len(frame) != 5 + length:
        raise FrameError("longueur_incoherente",
                         f"longueur incohérente : annoncé {length}, reçu {len(frame) - 5}")
    body, fcs = frame[1:-2], int.from_bytes(frame[-2:], "little")
    if _crc(body) != fcs:
        raise FrameError("crc_invalide", "CRC invalide")
    return body[2:]
