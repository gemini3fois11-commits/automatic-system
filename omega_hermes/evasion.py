"""Robustesse adversariale de BOB (blueprint §4.2, §6.2) : un attaquant baisse l'amplitude
de son canal caché pour passer sous le seuil. Grille : 2 canaux × 8 amplitudes × 60 = 960.

Le taux global dépend entièrement de la grille choisie ; la mesure utile est la courbe
par amplitude et l'amplitude la plus faible encore détectée à 100 %.
"""

import numpy as np

from omega_hermes.alice import AMPLITUDE, ELECTRIQUE, TEMPOREL
from omega_hermes.commun import Banc, impulsions
from omega_hermes.twin import CLASSES, Flux

FLUX_EVASION = 5
AMPLITUDES = (0.8, 0.4, 0.2, 0.1, 0.05, 0.03, 0.02, 0.01)


def grille(banc: Banc, repetitions: int = 60) -> dict:
    rng = Flux(banc.graine, FLUX_EVASION).suivant()
    courbe = {}
    total = evasions = 0
    for canal in ("COVERT", "DRAFT"):
        for amp in AMPLITUDES:
            X = []
            for i in range(repetitions):
                x = banc.twin.observer(CLASSES[i % 3])
                train = impulsions(rng, amp)
                x[ELECTRIQUE] += train
                if canal == "COVERT":
                    x[TEMPOREL] += train
                X.append(x)
            decisions, *_ = banc.juger(np.stack(X))
            passes = sum(Banc.accepte(d) for d in decisions)
            courbe[f"{canal}@{amp}"] = passes / repetitions
            total += repetitions
            evasions += passes
    plancher = {c: min((a for a in AMPLITUDES if courbe[f"{c}@{a}"] == 0.0), default=None)
                for c in ("COVERT", "DRAFT")}
    return {"cas": total, "evasions": evasions, "taux_global": evasions / total,
            "courbe": courbe, "amplitude_min_detectee_100pct": plancher,
            "amplitude_reference": AMPLITUDE,
            "taux_a_amplitude_reference": {c: courbe[f"{c}@{AMPLITUDE}"] for c in ("COVERT", "DRAFT")}}
