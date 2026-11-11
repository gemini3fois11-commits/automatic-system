"""ALICE — red team synthétique (blueprint §4.2, §4.4).

- Perturbations qui gardent la classe : bruit, jitter, dérive.
- Artefacts de capteur, qui produisent des plateaux : écrêtage, dropout → ARTIFACT.
- Familles étrangères, jamais vues à l'entraînement : chirp, carré → UNKNOWN.
- Canaux cachés : COVERT (impulsions synchronisées sur temporel + électrique)
  et DRAFT (impulsions sur l'électrique seule).

Aucun accès au réel (vérifié par omega_hermes.decouplage).
"""

import numpy as np

from omega_hermes.twin import CLASSES, MODALITES, N, Flux, Twin

FLUX_ALICE = 1
ARTIFACT, UNKNOWN, COVERT, DRAFT = "ARTIFACT", "UNKNOWN", "COVERT", "DRAFT"
LABELS = CLASSES + (ARTIFACT, UNKNOWN, COVERT, DRAFT)
TEMPOREL, ELECTRIQUE = MODALITES.index("temporel"), MODALITES.index("electrique")

# Canal caché (§4.4) : période 32, largeur 3, amplitude 0,8, même phase seedée.
PERIODE, LARGEUR, AMPLITUDE = 32, 3, 0.8

# Perturbations « douces » : elles ne doivent pas changer la classe.
BRUIT_DOUX, JITTER_ECHANTILLONS, DERIVE_MAX = 0.02, 0.15, 0.02

# Composition d'un lot de 200 : (label, famille, effectif).
MIX_200 = (
    ("CONNU", "aucune", 20), ("CONNU", "bruit", 20), ("CONNU", "jitter", 20), ("CONNU", "derive", 20),
    (ARTIFACT, "ecretage", 15), (ARTIFACT, "dropout", 15),
    (UNKNOWN, "chirp", 15), (UNKNOWN, "carre", 15),
    (COVERT, "tableau", 30), (DRAFT, "brouillons", 30),
)


def impulsions(rng: np.random.Generator) -> np.ndarray:
    train = np.zeros(N)
    for k in range(int(rng.integers(0, PERIODE)), N, PERIODE):
        train[k:k + LARGEUR] = AMPLITUDE
    return train


class Alice:
    def __init__(self, twin: Twin, graine: int = 7):
        self.twin = twin
        self._flux = Flux(graine, FLUX_ALICE)

    # — perturbations qui gardent la classe
    @staticmethod
    def bruit(x, rng):
        return x + rng.normal(0, BRUIT_DOUX, x.shape) * x.std(axis=1, keepdims=True)

    @staticmethod
    def jitter(x, rng):
        t = np.arange(N, dtype=float)
        return np.stack([np.interp(t + rng.uniform(-JITTER_ECHANTILLONS, JITTER_ECHANTILLONS, N), t, m) for m in x])

    @staticmethod
    def derive(x, rng):
        pente = rng.uniform(-DERIVE_MAX, DERIVE_MAX, (x.shape[0], 1)) * np.maximum(x.std(axis=1, keepdims=True), 0.1)
        return x + pente * np.linspace(0, 1, N)

    # — artefacts de capteur (plateaux)
    @staticmethod
    def ecretage(x, rng):
        x = x.copy()
        for m in rng.choice(len(MODALITES), size=int(rng.integers(1, 3)), replace=False):
            centre = x[m].mean()
            s = rng.uniform(0.5, 0.75) * np.abs(x[m] - centre).max()
            x[m] = np.clip(x[m], centre - s, centre + s)
        return x

    @staticmethod
    def dropout(x, rng):
        x = x.copy()
        m, longueur = int(rng.integers(0, len(MODALITES))), int(rng.integers(12, 41))
        debut = int(rng.integers(0, N - longueur))
        x[m, debut:debut + longueur] = 0.0
        return x

    # — familles étrangères
    @staticmethod
    def chirp(rng):
        t = np.arange(N)
        x = np.empty((len(MODALITES), N))
        for m in range(len(MODALITES)):
            fa = rng.uniform(2, 40)
            fb = fa + rng.uniform(30, 80)  # un vrai balayage, pas une quasi-sinusoïde
            phase = 2 * np.pi * (fa * t + (fb - fa) * t ** 2 / (2 * N)) / N
            x[m] = rng.uniform(0.5, 1.5) * np.sin(phase + rng.uniform(0, 2 * np.pi)) + rng.normal(0, 0.02, N)
        return x

    @staticmethod
    def carre(rng):
        """Source numérique étrangère : niveaux exacts, donc plateaux (piège du §4.3)."""
        t = np.arange(N)
        return np.stack([rng.uniform(0.5, 1.5) * np.sign(np.sin(2 * np.pi * rng.uniform(3, 30) * t / N
                                                                 + rng.uniform(0, 2 * np.pi)))
                         for _ in MODALITES])

    # — canaux cachés
    @staticmethod
    def covert(x, rng):
        x = x.copy()
        train = impulsions(rng)        # même phase sur les deux modalités : la coordination
        x[TEMPOREL] += train
        x[ELECTRIQUE] += train
        return x

    @staticmethod
    def draft(x, rng):
        x = x.copy()
        x[ELECTRIQUE] += impulsions(rng)  # on écrit sans envoyer : le temporel reste nominal
        return x

    def scenario(self, label: str, famille: str, classe: str):
        """Retourne (observation, label attendu)."""
        rng = self._flux.suivant()
        if label == UNKNOWN:
            return (self.chirp(rng) if famille == "chirp" else self.carre(rng)), UNKNOWN
        x = self.twin.observer(classe)
        if label == "CONNU":
            if famille != "aucune":
                x = getattr(self, famille)(x, rng)
            return x, classe
        if label == ARTIFACT:
            return getattr(self, famille)(x, rng), ARTIFACT
        if label == COVERT:
            return self.covert(x, rng), COVERT
        return self.draft(x, rng), DRAFT

    def lot(self, n: int = 200):
        """Un lot mélangé dont la composition suit MIX_200 (mise à l'échelle de n)."""
        rng = self._flux.suivant()
        plan = []
        for label, famille, effectif in MIX_200:
            plan += [(label, famille)] * round(effectif * n / 200)
        plan = [plan[i] for i in rng.permutation(len(plan))]
        X, labels, familles = [], [], []
        for i, (label, famille) in enumerate(plan):
            x, y = self.scenario(label, famille, CLASSES[i % len(CLASSES)])
            X.append(x)
            labels.append(y)
            familles.append(famille)
        return np.stack(X), labels, familles
