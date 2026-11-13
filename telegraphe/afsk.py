"""Modem AFSK Bell 202 (blueprint §8.2).

Mark 1200 Hz, space 2200 Hz, 1200 bauds, codage NRZI, modulation FSK à phase
continue. Démodulation par filtres de Goertzel à 1200 et 2200 Hz, une fenêtre
par bit. Export WAV PCM 16 bits mono.

NRZI (comme AX.25) : un bit **0** change de ton, un bit **1** garde le ton. Le
flux entier (fanions compris) est codé NRZI avant modulation, décodé après.

Honnêteté : la démodulation aligne ses fenêtres sur le débit **connu** du flux
généré ici — aucune récupération d'horloge en aveugle. C'est suffisant pour un
aller-retour en mémoire ou via un fichier WAV, pas pour une voie radio/micro
réelle. La voie microphone reste `[EXPÉRIMENTAL]`, non implémentée : ne pas la
promettre (blueprint §8.2).
"""

import io
import math
import struct
import wave

F_MARK = 1200
F_SPACE = 2200
BAUD = 1200
FS = 48000                       # 40 échantillons/bit exactement → fenêtres de Goertzel propres
AMPLITUDE = 0.7                  # pleine échelle évitée pour ne pas saturer au mélange


def echantillons_par_bit(fs: int = FS, baud: int = BAUD) -> float:
    return fs / baud


def _nrzi(bits: list[int], ton_initial: int = 1) -> list[int]:
    """bits logiques → suite de tons (1 = mark, 0 = space). 0 bascule, 1 maintient."""
    ton, tons = ton_initial, []
    for bit in bits:
        if bit == 0:
            ton ^= 1
        tons.append(ton)
    return tons


def _nrzi_inverse(tons: list[int], ton_initial: int = 1) -> list[int]:
    bits, precedent = [], ton_initial
    for ton in tons:
        bits.append(1 if ton == precedent else 0)
        precedent = ton
    return bits


def moduler(bits: list[int], *, fs: int = FS, baud: int = BAUD,
            amplitude: float = AMPLITUDE) -> list[float]:
    """Flux de bits → échantillons [-1, 1], phase continue entre bits."""
    spb = fs / baud
    tons = _nrzi(bits)
    ech, phase = [], 0.0
    n_emis = 0
    for i, ton in enumerate(tons):
        f = F_MARK if ton == 1 else F_SPACE
        # Bornes exactes du bit, pour éviter la dérive d'arrondi sur un spb fractionnaire.
        fin = round((i + 1) * spb)
        for _ in range(fin - n_emis):
            ech.append(amplitude * math.sin(phase))
            phase += 2 * math.pi * f / fs
        n_emis = fin
    return ech


def _goertzel(fenetre: list[float], f: float, fs: int) -> float:
    """Énergie du filtre de Goertzel à la fréquence f sur la fenêtre."""
    w = 2 * math.pi * f / fs
    coeff = 2 * math.cos(w)
    s1 = s2 = 0.0
    for x in fenetre:
        s0 = x + coeff * s1 - s2
        s2, s1 = s1, s0
    return s1 * s1 + s2 * s2 - coeff * s1 * s2


def demoduler(ech: list[float], n_bits: int, *, fs: int = FS, baud: int = BAUD) -> list[int]:
    """Échantillons → bits logiques. `n_bits` = nombre de bits émis (débit connu)."""
    spb = fs / baud
    tons = []
    for i in range(n_bits):
        a, b = round(i * spb), round((i + 1) * spb)
        fenetre = ech[a:b]
        if not fenetre:
            break
        p_mark = _goertzel(fenetre, F_MARK, fs)
        p_space = _goertzel(fenetre, F_SPACE, fs)
        tons.append(1 if p_mark >= p_space else 0)
    return _nrzi_inverse(tons)


def vers_wav_octets(ech: list[float], *, fs: int = FS) -> bytes:
    """Échantillons [-1, 1] → octets d'un fichier WAV PCM 16 bits mono."""
    tampon = io.BytesIO()
    with wave.open(tampon, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(fs)
        cadre = b"".join(struct.pack("<h", max(-32768, min(32767, round(x * 32767))))
                         for x in ech)
        w.writeframes(cadre)
    return tampon.getvalue()


def depuis_wav_octets(octets: bytes) -> tuple[list[float], int]:
    """Octets WAV → (échantillons [-1, 1], fréquence)."""
    with wave.open(io.BytesIO(octets), "rb") as w:
        if w.getsampwidth() != 2 or w.getnchannels() != 1:
            raise ValueError("WAV attendu : PCM 16 bits mono")
        fs = w.getframerate()
        cadre = w.readframes(w.getnframes())
    vals = struct.unpack("<%dh" % (len(cadre) // 2), cadre)
    return [v / 32767 for v in vals], fs
