"""TWIN — jumeau numérique synthétique (blueprint §4.2).

Cinq modalités de 256 échantillons et trois régimes connus. Chaque observation
tire ses paramètres d'un flux pseudo-aléatoire qui lui est propre
(SeedSequence [graine, flux, compteur]) : jamais deux fois le même signal.

Aucun accès au réel : ce module n'importe que numpy et n'ouvre ni fichier, ni
socket, ni capteur. C'est vérifié statiquement (omega_hermes.decouplage).
"""

import numpy as np

N = 256
MODALITES = ("audio", "vibration", "optique", "temporel", "electrique")
CLASSES = ("REPOS", "CHARGE", "RESONANCE")
FLUX_TWIN = 0

# Par régime et par modalité : (bin de la fondamentale, amplitude, niveau continu).
PROFILS = {
    "REPOS":     ((10, 0.5, 0.0), (4, 0.3, 0.0), (3, 0.4, 1.0), (7, 0.5, 0.0), (16, 0.5, 0.0)),
    "CHARGE":    ((22, 1.0, 0.0), (9, 0.8, 0.0), (6, 0.7, 1.5), (13, 0.8, 0.0), (28, 0.9, 0.0)),
    "RESONANCE": ((35, 0.7, 0.0), (17, 1.2, 0.0), (11, 0.5, 0.6), (21, 0.6, 0.0), (40, 0.7, 0.0)),
}
VARIATION_FREQUENCE = 0.06   # ± relatif
VARIATION_AMPLITUDE = 0.10   # ± relatif
BRUIT_RELATIF = 0.04         # écart-type du bruit / amplitude nominale
HARMONIQUE = 0.3             # poids de la 2e harmonique


class Flux:
    """Générateur de flux numpy indépendants, jamais réutilisés."""

    def __init__(self, graine: int, flux: int):
        self.graine, self.flux, self.compteur = graine, flux, 0

    def suivant(self) -> np.random.Generator:
        ss = np.random.SeedSequence([self.graine, self.flux, self.compteur])
        self.compteur += 1
        return np.random.default_rng(ss)


class Twin:
    def __init__(self, graine: int = 7):
        self._flux = Flux(graine, FLUX_TWIN)

    def observer(self, classe: str) -> np.ndarray:
        """Une observation (5, 256) du régime `classe`."""
        rng = self._flux.suivant()
        t = np.arange(N)
        x = np.empty((len(MODALITES), N))
        for m, (f0, a0, niveau) in enumerate(PROFILS[classe]):
            f = f0 * rng.uniform(1 - VARIATION_FREQUENCE, 1 + VARIATION_FREQUENCE)
            a = a0 * rng.uniform(1 - VARIATION_AMPLITUDE, 1 + VARIATION_AMPLITUDE)
            phi1, phi2 = rng.uniform(0, 2 * np.pi, 2)
            x[m] = (niveau * rng.uniform(0.95, 1.05)
                    + a * (np.sin(2 * np.pi * f * t / N + phi1)
                           + HARMONIQUE * np.sin(4 * np.pi * f * t / N + phi2))
                    + rng.normal(0, BRUIT_RELATIF * a0, N))
        return x

    def lot(self, classes) -> np.ndarray:
        return np.stack([self.observer(c) for c in classes])
