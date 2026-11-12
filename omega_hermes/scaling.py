"""Coûts d'échelle de HERMÈS (blueprint §6.2) : mesurés, ordonnés, bornés explicitement.

P-MES-26 : horloge monotone brute, médiane sur de nombreuses itérations, plancher mesuré
et soustrait. Le résultat est une borne pour CETTE machine, pas une loi universelle.
"""

import os
import time

import numpy as np

from omega_hermes.bob import plateaux
from omega_hermes.commun import Banc
from omega_hermes.eyes import traits
from omega_hermes.twin import CLASSES
from plateforme_omega.commun import conclure, sortir

DOSSIER = os.path.dirname(os.path.abspath(__file__))
BATTEMENT_S = 5
BUDGET_CPU = 0.5


def mediane_ms(f, n):
    plancher = []
    for _ in range(1000):
        t0 = time.perf_counter_ns()
        plancher.append(time.perf_counter_ns() - t0)
    p = float(np.median(plancher))
    mesures = []
    for _ in range(n):
        t0 = time.perf_counter_ns()
        f()
        mesures.append(time.perf_counter_ns() - t0 - p)
    return float(np.median(mesures)) / 1e6


def mesurer(graine=7) -> dict:
    banc = Banc(graine)
    X = banc.twin.lot([CLASSES[i % 3] for i in range(1000)])
    Z = banc.std.transformer(traits(X))
    x1, z1 = X[:1], Z[:1]
    etapes = {"plateaux": mediane_ms(lambda: plateaux(x1), 300),
              "traits (FFT radix-2 comprise)": mediane_ms(lambda: traits(x1), 300),
              "standardisation": mediane_ms(lambda: banc.std.transformer(traits(x1)), 300)
              - mediane_ms(lambda: traits(x1), 300),
              "distances de Mahalanobis": mediane_ms(lambda: banc.bob.distances(z1), 300)}
    lots = {}
    for b in (1, 10, 100, 1000):
        Xb = X[:b]
        lots[b] = mediane_ms(lambda Y=Xb: banc.bob.decider(Y, banc.std.transformer(traits(Y))),
                             20 if b == 1000 else 60) / b
    pente, ordonnee = np.polyfit([1, 10, 100, 1000],
                                 [lots[b] * b for b in (1, 10, 100, 1000)], 1)
    noeuds_max = int(BUDGET_CPU * BATTEMENT_S * 1000 / lots[1000])
    return {"etapes_ms": dict(sorted(etapes.items(), key=lambda kv: kv[1])),
            "par_observation_ms_selon_lot": {str(b): v for b, v in lots.items()},
            "modele_lineaire_ms": {"fixe": float(ordonnee), "par_observation": float(pente)},
            "borne": {"battement_s": BATTEMENT_S, "budget_cpu": BUDGET_CPU,
                      "noeuds_max_par_battement": noeuds_max, "machine": os.uname().machine,
                      "coeurs": os.cpu_count()}}


def main() -> int:
    m = mesurer()
    lots = m["par_observation_ms_selon_lot"]
    return conclure("scaling", [
        ("coûts par étape mesurés et ordonnés", len(m["etapes_ms"]) == 4, " < ".join(m["etapes_ms"])),
        ("le traitement par lot amortit le coût fixe (lot 1000 < lot 1)", lots["1000"] < lots["1"],
         f"{lots['1']:.3f} → {lots['1000']:.4f} ms par observation"),
        ("borne explicite : nœuds par battement de 5 s à 50 % de CPU", m["borne"]["noeuds_max_par_battement"] > 8,
         f"{m['borne']['noeuds_max_par_battement']} nœuds"),
    ], m, ["Mesures sur une machine précise (voir execution.plateforme) ; elles ne se transposent pas.",
           "Un seul cœur utilisé : la borne est celle d'un processus Python + numpy."], dossier=DOSSIER)


if __name__ == "__main__":
    sortir(main())
