"""BOB — décideur défensif à deux seuils (blueprint §4.3).

1. Test d'artefact : plateaux exacts (écrêtage, dropout).
2. Distance de Mahalanobis (covariance diagonale) à chaque classe connue.
3. Seuil strict = 99e percentile des distances d'entraînement : en dessous, et
   sans artefact, classe la plus proche.
4. Seuil lâche = 100 × seuil strict : entre les deux (ou artefact) → ARTIFACT ;
   au-delà → UNKNOWN, même si le signal a des plateaux.

La règle historique à seuil unique (`regle="seuil_unique"`) est conservée pour
reproduire le défaut documenté : une onde carrée étrangère y sort ARTIFACT au
lieu d'UNKNOWN — rejetée, donc bon score, mais pour la mauvaise raison.
"""

import numpy as np

from omega_hermes.alice import ARTIFACT, UNKNOWN
from omega_hermes.twin import CLASSES

SEUIL_PLATEAUX = 0.03  # part d'échantillons consécutifs exactement égaux, dans une modalité


def plateaux(X) -> np.ndarray:
    X = np.asarray(X)
    if X.ndim == 2:
        X = X[None]
    return ((np.diff(X, axis=-1) == 0).mean(-1) > SEUIL_PLATEAUX).any(-1)


class Bob:
    def __init__(self, percentile: float = 99.0, facteur_lache: float = 100.0,
                 plancher_variance: float = 1e-3, regle: str = "deux_seuils"):
        if regle not in ("deux_seuils", "seuil_unique"):
            raise ValueError(f"règle inconnue : {regle}")
        self.percentile, self.facteur_lache = percentile, facteur_lache
        self.plancher_variance, self.regle = plancher_variance, regle

    def entrainer(self, Z: np.ndarray, classes) -> "Bob":
        classes = np.asarray(classes)
        self.mu = np.stack([Z[classes == c].mean(0) for c in CLASSES])
        self.var = np.stack([np.maximum(Z[classes == c].var(0), self.plancher_variance)
                             for c in CLASSES])
        propre = self.distances(Z)[np.arange(len(Z)), [CLASSES.index(c) for c in classes]]
        self.seuil_strict = float(np.percentile(propre, self.percentile))
        self.distances_entrainement = propre
        return self

    @property
    def seuil_lache(self) -> float:
        return self.facteur_lache * self.seuil_strict

    def distances(self, Z) -> np.ndarray:
        Z = np.atleast_2d(Z)
        return (((Z[:, None, :] - self.mu[None]) ** 2) / self.var[None]).sum(-1)

    def decider(self, X, Z) -> tuple[list[str], np.ndarray]:
        d = self.distances(Z)
        proche, dmin = d.argmin(1), d.min(1)
        art = plateaux(X)
        decisions = []
        for k, dist, a in zip(proche, dmin, art):
            if self.regle == "seuil_unique":
                decision = CLASSES[k] if (dist < self.seuil_strict and not a) else (ARTIFACT if a else UNKNOWN)
            elif dist >= self.seuil_lache:
                decision = UNKNOWN
            elif a or dist >= self.seuil_strict:
                decision = ARTIFACT
            else:
                decision = CLASSES[k]
            decisions.append(decision)
        return decisions, dmin
