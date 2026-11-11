"""Banc commun de la phase 4 : un BOB entraîné une fois, comme dans la boucle (§4)."""

import numpy as np

from omega_hermes.alice import PERIODE, Alice
from omega_hermes.bob import Bob, plateaux
from omega_hermes.eyes import Standardiseur, traits
from omega_hermes.twin import CLASSES, N, Twin


class Banc:
    def __init__(self, graine: int = 7, par_classe: int = 150):
        self.graine = graine
        self.twin = Twin(graine)
        self.alice = Alice(self.twin, graine)
        classes = [CLASSES[i % len(CLASSES)] for i in range(par_classe * len(CLASSES))]
        X = self.twin.lot(classes)
        self.std = Standardiseur().ajuster(traits(X))
        self.bob = Bob().entrainer(self.std.transformer(traits(X)), classes)
        self.appels_bob = 0

    def juger(self, X):
        """Décisions, distances, traits et plateaux pour un lot (B, 5, N)."""
        X = np.asarray(X)
        if X.ndim == 2:
            X = X[None]
        self.appels_bob += 1
        T = traits(X)
        decisions, dmin = self.bob.decider(X, self.std.transformer(T))
        return decisions, dmin, T, plateaux(X)

    @staticmethod
    def accepte(decision: str) -> bool:
        return decision in CLASSES


def impulsions(rng, amplitude: float, periode: int = PERIODE, largeur: int = 3) -> np.ndarray:
    train = np.zeros(N)
    for k in range(int(rng.integers(0, periode)), N, periode):
        train[k:k + largeur] = amplitude
    return train
