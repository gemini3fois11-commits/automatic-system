"""EYES — fusion multimodale en 31 traits (blueprint §4.2).

6 descripteurs par modalité (moyenne, écart-type, facteur de crête, kurtosis,
fréquence dominante, centroïde spectral) + 1 trait croisé (corrélation de
Pearson temporel × électrique) = 31 traits. FFT radix-2 écrite à la main, sans
numpy.fft, pour pouvoir être portée à l'identique en JavaScript.
"""

import numpy as np

from omega_hermes.twin import MODALITES, N

DESCRIPTEURS = ("moyenne", "ecart_type", "crete", "kurtosis", "f_dominante", "centroide")
NOMS_TRAITS = tuple(f"{m}.{d}" for m in MODALITES for d in DESCRIPTEURS) + ("xcorr_temporel_electrique",)
TEMPOREL, ELECTRIQUE = MODALITES.index("temporel"), MODALITES.index("electrique")


def _bits_inverses(n: int) -> np.ndarray:
    bits = n.bit_length() - 1
    return np.array([int(f"{i:0{bits}b}"[::-1], 2) for i in range(n)])


def fft_radix2(x) -> np.ndarray:
    """FFT de Cooley-Tukey itérative en base 2 sur le dernier axe."""
    x = np.asarray(x, dtype=complex)
    n = x.shape[-1]
    if n < 1 or n & (n - 1):
        raise ValueError("la longueur doit être une puissance de 2")
    X = x[..., _bits_inverses(n)]
    forme = X.shape[:-1]
    m = 2
    while m <= n:
        moitie = m // 2
        w = np.exp(-2j * np.pi * np.arange(moitie) / m)
        blocs = X.reshape(forme + (n // m, m))
        a, b = blocs[..., :moitie], blocs[..., moitie:] * w
        X = np.concatenate([a + b, a - b], axis=-1).reshape(forme + (n,))
        m *= 2
    return X


def traits(X) -> np.ndarray:
    """(B, 5, N) ou (5, N) → (B, 31)."""
    X = np.asarray(X, dtype=float)
    if X.ndim == 2:
        X = X[None]
    moyenne = X.mean(-1)
    centre = X - moyenne[..., None]
    ecart = np.maximum(X.std(-1), 1e-12)
    crete = np.abs(centre).max(-1) / ecart
    kurtosis = (centre ** 4).mean(-1) / ecart ** 4 - 3
    spectre = np.abs(fft_radix2(X))[..., 1:N // 2 + 1]
    k = np.arange(1, N // 2 + 1)
    f_dom = (spectre.argmax(-1) + 1) / (N / 2)
    centroide = (spectre * k).sum(-1) / np.maximum(spectre.sum(-1), 1e-12) / (N / 2)
    par_modalite = np.stack([moyenne, ecart, crete, kurtosis, f_dom, centroide], axis=-1)
    a, b = centre[:, TEMPOREL], centre[:, ELECTRIQUE]
    r = (a * b).mean(-1) / (ecart[:, TEMPOREL] * ecart[:, ELECTRIQUE])
    return np.concatenate([par_modalite.reshape(len(X), -1), r[:, None]], axis=1)


class Standardiseur:
    """Standardisation apprise sur l'entraînement uniquement."""

    def ajuster(self, T: np.ndarray) -> "Standardiseur":
        self.moyenne = T.mean(0)
        self.ecart = np.maximum(T.std(0), 1e-9)
        return self

    def transformer(self, T: np.ndarray) -> np.ndarray:
        return (T - self.moyenne) / self.ecart
