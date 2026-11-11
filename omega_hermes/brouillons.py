"""Brouillons (blueprint §4.4, §6.2) : le canal DRAFT, isolé.

DRAFT écrit sur l'électrique sans « envoyer » sur le temporel : sa signature est le
découplage. On mesure son rejet, puis on vérifie qu'on le distingue de COVERT par le
trait 31 (corrélation temporel × électrique), sans que BOB ait à le nommer.
"""

import numpy as np

from omega_hermes.commun import Banc
from omega_hermes.twin import CLASSES, Flux

FLUX_BROUILLONS = 6
SEUIL_XCORR = 0.1


def isoler(banc: Banc, n: int = 100) -> dict:
    rng = Flux(banc.graine, FLUX_BROUILLONS).suivant()
    lots = {"nominal": [], "DRAFT": [], "COVERT": []}
    for i in range(n):
        base = lambda: banc.twin.observer(CLASSES[i % 3])
        lots["nominal"].append(base())
        lots["DRAFT"].append(banc.alice.draft(base(), rng))
        lots["COVERT"].append(banc.alice.covert(base(), rng))
    res = {}
    for nom, X in lots.items():
        decisions, _, T, _ = banc.juger(np.stack(X))
        res[nom] = {"rejet": float(np.mean([not Banc.accepte(d) for d in decisions])),
                    "xcorr_mediane": float(np.median(T[:, -1])), "xcorr": T[:, -1]}
    draft_ok = np.mean(res["DRAFT"]["xcorr"] < SEUIL_XCORR)
    covert_ok = np.mean(res["COVERT"]["xcorr"] >= SEUIL_XCORR)
    for v in res.values():
        del v["xcorr"]
    return {**res, "discrimination_draft_vs_covert": float((draft_ok + covert_ok) / 2),
            "seuil_xcorr": SEUIL_XCORR}
