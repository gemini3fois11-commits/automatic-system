"""Voie microphone — récepteur AFSK à synchronisation aveugle (blueprint §8.2).

`[EXPÉRIMENTAL]`, et le restera : vérifié uniquement sur une **boucle locale**
dégradée (bruit, décalage, gain, composante continue, silences ajoutés), jamais
sur un vrai canal acoustique dans ce conteneur. Le blueprint interdit de la
promettre (§8.2) ; on ne la promet pas.

Ce que `afsk.demoduler` suppose et qu'un micro n'offre pas : des fenêtres de bit
alignées sur un début connu. Ici le début n'est pas donné. Le récepteur :

  1. retire la composante continue et normalise l'amplitude (AGC simple) ;
  2. trouve le début du signal par l'énergie (seuil sur le RMS glissant) ;
  3. cherche la phase sous-bit : il essaie quelques décalages autour du début et
     accepte la **première trame validée par le CRC** — le CRC-16/X-25 est
     l'oracle de synchronisation (une fausse synchro ne passe pas le CRC).

Ce qu'il ne fait **pas** : corriger un écart de fréquence d'échantillonnage ou
une dérive d'horloge (pas de resynchronisation en cours de trame), ni séparer
plusieurs trames d'un flux continu. La capture elle-même (micro → échantillons)
est au programme de l'appelant : aucune dépendance audio n'est imposée ici.
"""

import math

from telegraphe import afsk, trame


def _sans_continu(ech: list[float]) -> list[float]:
    moyenne = sum(ech) / len(ech) if ech else 0.0
    return [x - moyenne for x in ech]


def _normaliser(ech: list[float]) -> list[float]:
    crete = max((abs(x) for x in ech), default=0.0)
    if crete == 0:
        return ech
    return [x / crete for x in ech]


def _debut_bande(ech: list[float], spb: float, fs: int, seuil_rel: float = 0.25) -> int:
    """Premier échantillon où l'énergie **dans la bande** (mark + space) s'allume.

    On mesure la puissance de Goertzel à 1200 et 2200 Hz sur une fenêtre d'un bit,
    glissée par pas. Une composante continue ou un silence n'a aucune énergie à ces
    fréquences : contrairement au RMS brut, cette détection ignore le niveau continu.
    """
    fen = max(8, int(spb))
    pas = max(1, fen // 4)
    bande, debuts = [], []
    for i in range(0, len(ech) - fen, pas):
        f = ech[i:i + fen]
        bande.append(afsk._goertzel(f, afsk.F_MARK, fs) + afsk._goertzel(f, afsk.F_SPACE, fs))
        debuts.append(i)
    if not bande:
        return 0
    seuil = seuil_rel * max(bande)
    for i, p in enumerate(bande):
        if p >= seuil:
            return debuts[i]
    return 0


def recevoir_flux(ech: list[float], *, fs: int = afsk.FS, baud: int = afsk.BAUD,
                  marge_phase: float = 1.0) -> tuple[bytes, int]:
    """Flux audio brut → (octets utiles, décalage de début retenu).

    Lève trame.TrameInvalide('sync_echouee') si aucune phase ne donne de trame
    validée par le CRC. `marge_phase` élargit la fenêtre de recherche (en bits).
    """
    if not ech:
        raise trame.TrameInvalide("flux_vide")
    spb = fs / baud
    signal = _normaliser(_sans_continu(ech))
    debut = _debut_bande(signal, spb, fs)
    fenetre = int(spb * (1 + marge_phase))
    # Essayer les décalages du plus proche du début estimé au plus lointain : le
    # `start` retenu est alors l'alignement validé par le CRC le plus proche de
    # l'allumage de bande, pas le premier venu.
    deltas = sorted(range(-fenetre, fenetre + 1), key=abs)
    for delta in deltas:
        start = debut + delta
        if start < 0 or start >= len(signal):
            continue
        reste = signal[start:]
        n_bits = int(len(reste) / spb)
        if n_bits < 24:
            continue
        try:
            octets = trame.analyser(afsk.demoduler(reste, n_bits, fs=fs, baud=baud))
        except trame.TrameInvalide:
            continue
        return octets, start
    raise trame.TrameInvalide("sync_echouee")


# ------- outils de banc : simuler une dégradation « acoustique » (boucle locale) -------

def degrader(ech: list[float], *, rng, snr_db: float | None = None, gain: float = 1.0,
             continu: float = 0.0, silence_avant: int = 0, silence_apres: int = 0) -> list[float]:
    """Applique bruit blanc (à un SNR donné), gain, composante continue et silences.

    Dégradation synthétique pour la boucle locale — ce n'est PAS un vrai micro.
    """
    sortie = list(ech)
    if snr_db is not None:
        puissance = sum(x * x for x in ech) / len(ech)
        sigma = math.sqrt(puissance / (10 ** (snr_db / 10))) if puissance > 0 else 0.0
        sortie = [x + rng.gauss(0, sigma) for x in sortie]
    sortie = [x * gain + continu for x in sortie]
    return [0.0] * silence_avant + sortie + [0.0] * silence_apres
