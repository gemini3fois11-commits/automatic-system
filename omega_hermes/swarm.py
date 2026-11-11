"""Essaim (blueprint §4.2, §4.5) : 8 nœuds, un battement toutes les 5 s simulées.

À partir du battement 10, deux nœuds ouvrent un canal COVERT et un nœud un canal
DRAFT. Chaque battement, chaque nœud émet une observation que BOB juge. On mesure
la latence de détection (en battements), le nombre de messages cachés émis, l'ampleur
de la compromission et le taux de fausses alarmes sur les nœuds sains.
"""

import numpy as np

from omega_hermes.alice import COVERT, DRAFT, PERIODE
from omega_hermes.commun import Banc
from omega_hermes.twin import CLASSES, N, Flux

BATTEMENT_S = 5
FLUX_ESSAIM = 3


def simuler(banc: Banc, *, noeuds=8, battements=40, depart=10, covert=2, draft=1) -> dict:
    rng = Flux(banc.graine, FLUX_ESSAIM).suivant()
    compromis = rng.choice(noeuds, size=covert + draft, replace=False)
    canal = {int(n): (COVERT if i < covert else DRAFT) for i, n in enumerate(compromis)}
    premiere_detection = {n: None for n in canal}
    fausses, saines, messages = 0, 0, 0
    for b in range(battements):
        X = []
        for n in range(noeuds):
            x = banc.twin.observer(CLASSES[n % len(CLASSES)])
            if n in canal and b >= depart:
                x = (banc.alice.covert if canal[n] == COVERT else banc.alice.draft)(x, rng)
                messages += N // PERIODE
            X.append(x)
        decisions, *_ = banc.juger(np.stack(X))
        for n, d in enumerate(decisions):
            rejete = not Banc.accepte(d)
            if n in canal and b >= depart:
                if rejete and premiere_detection[n] is None:
                    premiere_detection[n] = b
            else:
                saines += 1
                fausses += rejete
    latences = {f"N{n}": (None if premiere_detection[n] is None else premiere_detection[n] - depart)
                for n in canal}
    detectes = [l for l in latences.values() if l is not None]
    tous = bool(canal) and len(detectes) == len(canal)
    return {
        "noeuds": noeuds, "battements": battements, "depart": depart,
        "compromis": {f"N{n}": c for n, c in sorted(canal.items())},
        "latence_battements": latences,
        "tous_detectes": tous or not canal,
        "latence_max_battements": max(detectes) if tous else None,
        "latence_max_s": max(detectes) * BATTEMENT_S if tous else None,
        "messages_caches": messages,
        "ampleur": len(canal) / noeuds,
        "fausses_alarmes": fausses / saines if saines else 0.0,
        "observations_saines": saines,
    }


def balayage(banc: Banc) -> list[dict]:
    """4 niveaux de compromission (blueprint §6.1)."""
    niveaux = [(0, 0), (1, 0), (2, 1), (3, 2)]
    return [dict(simuler(banc, covert=c, draft=d), niveau=f"{c} COVERT + {d} DRAFT") for c, d in niveaux]
