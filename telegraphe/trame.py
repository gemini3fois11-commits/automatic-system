"""Trame HDLC et FCS CRC-16/X-25 (blueprint §8.2).

Couche bits, indépendante du son. Une trame est : un ou plusieurs fanions
`0x7E`, puis le contenu (octets de données suivis des deux octets de FCS,
chaque octet émis bit de poids faible d'abord), bourré de bits, puis un ou
plusieurs fanions de clôture. C'est la trame d'AX.25, sans l'adressage.

FCS : CRC-16/X-25 (polynôme 0x1021 réfléchi, init 0xFFFF, réflexion entrée et
sortie, ou-exclusif final 0xFFFF). Valeur de contrôle sur `b"123456789"` :
`0x906E` (vérifiée dans le test). Ce CRC détecte toute erreur d'un bit et toute
rafale d'au plus 16 bits ; il n'authentifie rien (l'authentification est le
sceau du témoin, pas le CRC — voir registre.py).
"""

FANION = 0x7E


def crc16_x25(donnees: bytes) -> int:
    """CRC-16/X-25, l'exact FCS de HDLC/AX.25."""
    crc = 0xFFFF
    for octet in donnees:
        crc ^= octet
        for _ in range(8):
            crc = (crc >> 1) ^ 0x8408 if crc & 1 else crc >> 1
    return crc ^ 0xFFFF


def _bits_lsb(octets: bytes) -> list[int]:
    """Chaque octet en bits, poids faible d'abord (convention AX.25)."""
    return [(octet >> i) & 1 for octet in octets for i in range(8)]


def _octets_depuis_bits_lsb(bits: list[int]) -> bytes:
    if len(bits) % 8 != 0:
        raise ValueError("nombre de bits non multiple de 8")
    sortie = bytearray()
    for base in range(0, len(bits), 8):
        octet = 0
        for i in range(8):
            octet |= (bits[base + i] & 1) << i
        sortie.append(octet)
    return bytes(sortie)


def _bourrer(bits: list[int]) -> list[int]:
    """Après cinq 1 consécutifs, insère un 0 : le contenu ne peut pas imiter un fanion."""
    sortie, uns = [], 0
    for bit in bits:
        sortie.append(bit)
        uns = uns + 1 if bit == 1 else 0
        if uns == 5:
            sortie.append(0)
            uns = 0
    return sortie


def _debourrer(bits: list[int]) -> list[int] | None:
    """Retire les 0 de bourrage. Rend None si la séquence est malformée (0 attendu après cinq 1)."""
    sortie, uns, i = [], 0, 0
    while i < len(bits):
        bit = bits[i]
        if uns == 5:
            if bit != 0:
                return None  # 111110 imposé par le bourrage ; 111111 = fanion, pas du contenu
            uns = 0
            i += 1
            continue
        sortie.append(bit)
        uns = uns + 1 if bit == 1 else 0
        i += 1
    return sortie


def _bits_fanion(n: int) -> list[int]:
    return _bits_lsb(bytes([FANION])) * n


def construire(donnees: bytes, *, fanions_tete: int = 4, fanions_queue: int = 2) -> list[int]:
    """Octets utiles → flux de bits prêt à moduler (fanions + contenu bourré + FCS)."""
    if fanions_tete < 1 or fanions_queue < 1:
        raise ValueError("au moins un fanion de chaque côté")
    fcs = crc16_x25(donnees)
    contenu = _bits_lsb(donnees + fcs.to_bytes(2, "little"))
    return _bits_fanion(fanions_tete) + _bourrer(contenu) + _bits_fanion(fanions_queue)


def _segments_entre_fanions(bits: list[int]) -> list[list[int]]:
    """Découpe le flux aux fanions 01111110 et rend les contenus bruts non vides."""
    motif = _bits_lsb(bytes([FANION]))
    positions = []
    i = 0
    while i + 8 <= len(bits):
        if bits[i:i + 8] == motif:
            positions.append(i)
            i += 8
        else:
            i += 1
    segments = []
    for a, b in zip(positions, positions[1:]):
        contenu = bits[a + 8:b]
        if contenu:
            segments.append(contenu)
    return segments


class TrameInvalide(ValueError):
    """Trame rejetée. `raison` est un identifiant stable."""

    def __init__(self, raison: str):
        super().__init__(raison)
        self.raison = raison


def analyser(bits: list[int]) -> bytes:
    """Flux de bits → octets utiles. Lève TrameInvalide si aucune trame saine n'est trouvée.

    Raisons stables : `aucun_fanion`, `bourrage_invalide`, `trame_trop_courte`,
    `longueur_non_octet`, `crc_invalide`.
    """
    segments = _segments_entre_fanions(bits)
    if not segments:
        raise TrameInvalide("aucun_fanion")
    derniere_raison = "aucun_fanion"
    for brut in segments:
        debourre = _debourrer(brut)
        if debourre is None:
            derniere_raison = "bourrage_invalide"
            continue
        if len(debourre) < 24:  # au moins FCS (16) + 1 octet
            derniere_raison = "trame_trop_courte"
            continue
        if len(debourre) % 8 != 0:
            derniere_raison = "longueur_non_octet"
            continue
        octets = _octets_depuis_bits_lsb(debourre)
        donnees, fcs_recu = octets[:-2], int.from_bytes(octets[-2:], "little")
        if crc16_x25(donnees) != fcs_recu:
            derniere_raison = "crc_invalide"
            continue
        return donnees
    raise TrameInvalide(derniere_raison)
