"""LOOP — boucle HERMÈS complète (blueprint §4.1, §12 phase 2).

SIMULER → PERTURBER → OBSERVER → FUSIONNER → VALIDER → MESURER → APPRENDRE → RÉPARER.

À chaque itération, le seuil strict de BOB se resserre si des anomalies ont été
acceptées (FPR > 0), se relâche si trop de connus sont rejetés (FNR > cible),
sinon il est maintenu. Chaque ajustement est inscrit dans une chaîne Γ du socle
de preuve.

Usage : python3 -m omega_hermes.loop [--graine 7] [--iterations 5] [--scenarios 200]
                                     [--entrainement 150] [--journal FICHIER] [--evidence FICHIER]
"""

import argparse
import collections
import os
import sys
import tempfile
import time

import numpy as np

from omega_hermes import decouplage
from omega_hermes.alice import COVERT, UNKNOWN, Alice
from omega_hermes.bob import Bob
from omega_hermes.eyes import Standardiseur, traits
from omega_hermes.hermes import mesurer
from omega_hermes.twin import CLASSES, Twin
from outils.evidence import GRAINE, ecrire
from socle_preuve.gamma import Chaine, verifier_chaine

CIBLE_FNR = 0.02
PAS_RESSERRER, PAS_RELACHER = 0.9, 1.1
BORNES_STRICT = (0.5, 2.0)   # relatif au seuil appris
SCORE_CIBLE, TOLERANCE = 0.98, 0.01


def _decider_un(bob, std, x):
    return bob.decider(x[None], std.transformer(traits(x)))[0][0]


def _latences_ms(bob, std, X) -> tuple[list[float], float]:
    """P-MES-26 : horloge monotone brute, médiane, plancher mesuré et soustrait."""
    plancher = []
    for _ in range(2000):
        t0 = time.perf_counter_ns()
        plancher.append(time.perf_counter_ns() - t0)
    plancher_ms = float(np.median(plancher)) / 1e6
    latences = []
    for x in X:
        t0 = time.perf_counter_ns()
        _decider_un(bob, std, x)
        latences.append((time.perf_counter_ns() - t0) / 1e6 - plancher_ms)
    return latences, plancher_ms


def boucle(graine=GRAINE, iterations=5, scenarios=200, entrainement=150, journal=None) -> dict:
    twin = Twin(graine)
    alice = Alice(twin, graine)
    classes = [CLASSES[i % len(CLASSES)] for i in range(entrainement * len(CLASSES))]
    X_train = twin.lot(classes)
    std = Standardiseur().ajuster(traits(X_train))
    Z_train = std.transformer(traits(X_train))
    bob = Bob().entrainer(Z_train, classes)
    historique = Bob(regle="seuil_unique").entrainer(Z_train, classes)
    strict_appris = bob.seuil_strict

    tous_labels, toutes_decisions, toutes_latences = [], [], []
    bandes = collections.defaultdict(list)
    xcorr = collections.defaultdict(list)
    carres = collections.Counter()
    iterations_res, ajustements = [], []
    for it in range(iterations):
        X, labels, familles = alice.lot(scenarios)
        T = traits(X)
        decisions, dmin = bob.decider(X, std.transformer(T))
        latences, plancher_ms = _latences_ms(bob, std, X)
        anciennes, _ = historique.decider(X, std.transformer(T))
        for lab, fam, d, r, dec_hist, dec in zip(labels, familles, dmin, T[:, -1],
                                                 anciennes, decisions):
            groupe = "CONNU" if lab in CLASSES else lab
            bandes[f"{groupe}/{fam}"].append(float(d))
            xcorr["nominal" if (groupe == "CONNU" and fam == "aucune") else groupe].append(float(r))
            if fam == "carre":
                carres[("seuil_unique", dec_hist)] += 1
                carres[("deux_seuils", dec)] += 1
        m = mesurer(labels, decisions, latences)
        tous_labels += labels
        toutes_decisions += decisions
        toutes_latences += latences

        avant = bob.seuil_strict
        if m["fpr"] > 0:
            action, raison = "RESSERRE", "anomalies_acceptees"
            bob.seuil_strict = max(avant * PAS_RESSERRER, BORNES_STRICT[0] * strict_appris)
        elif m["fnr"] > CIBLE_FNR:
            action, raison = "RELACHE", "connus_rejetes"
            bob.seuil_strict = min(avant * PAS_RELACHER, BORNES_STRICT[1] * strict_appris)
        else:
            action, raison = "MAINTIENT", "dans_la_cible"
        ajustement = {"iteration": it + 1, "action": action, "raison": raison,
                      "seuil_strict_avant": avant, "seuil_strict_apres": bob.seuil_strict,
                      "fpr": m["fpr"], "fnr": m["fnr"]}
        ajustements.append(ajustement)
        if journal is not None:
            journal.inscrire("ajustement", action, raison, ajustement)
        iterations_res.append({"iteration": it + 1, "score": m["score"], "ber": m["ber"],
                               "fpr": m["fpr"], "fnr": m["fnr"],
                               "rejet_inconnu": m["rejet_inconnu"],
                               "covert_rejection": m["covert_rejection"],
                               "draft_rejection": m["draft_rejection"],
                               "seuil_strict": avant, "seuil_lache": avant * bob.facteur_lache})

    total = mesurer(tous_labels, toutes_decisions, toutes_latences)
    total["latence_plancher_ms"] = plancher_ms
    n_carres = sum(v for (r, _), v in carres.items() if r == "seuil_unique")
    return {
        "global": total,
        "iterations": iterations_res,
        "ajustements": ajustements,
        "seuils_appris": {"strict": strict_appris, "lache": strict_appris * bob.facteur_lache,
                          "percentile": bob.percentile, "facteur_lache": bob.facteur_lache},
        "bandes_distance": {k: {"n": len(v), "min": min(v), "mediane": float(np.median(v)),
                                "max": max(v)} for k, v in sorted(bandes.items())},
        "trait_31_xcorr": {k: {"mediane": float(np.median(v)),
                               "mediane_abs": float(np.median(np.abs(v)))}
                           for k, v in sorted(xcorr.items())},
        "defaut_historique": {
            "carres": n_carres,
            "seuil_unique_artifact": carres[("seuil_unique", "ARTIFACT")] / n_carres,
            "seuil_unique_unknown": carres[("seuil_unique", UNKNOWN)] / n_carres,
            "deux_seuils_unknown": carres[("deux_seuils", UNKNOWN)] / n_carres,
        },
    }


def criteres(res: dict, violations: list, journal_ok: bool) -> list[tuple[str, bool, str]]:
    g = res["global"]
    d = res["defaut_historique"]
    return [
        (f"score ≥ {SCORE_CIBLE} (tolérance {TOLERANCE})", g["score"] >= SCORE_CIBLE - TOLERANCE,
         f"{g['score']:.4f}"),
        ("rejet inconnu = 1,000", g["rejet_inconnu"] == 1.0, f"{g['rejet_inconnu']:.3f}"),
        ("rejet COVERT = 1,000", g["covert_rejection"] == 1.0, f"{g['covert_rejection']:.3f}"),
        ("rejet DRAFT = 1,000", g["draft_rejection"] == 1.0, f"{g['draft_rejection']:.3f}"),
        ("FPR = 0", g["fpr"] == 0.0, f"{g['fpr']:.3f}"),
        ("défaut historique reproduit : carré → ARTIFACT au seuil unique",
         d["seuil_unique_artifact"] > 0.5, f"{d['seuil_unique_artifact']:.3f}"),
        ("défaut corrigé : carré → UNKNOWN à deux seuils", d["deux_seuils_unknown"] == 1.0,
         f"{d['deux_seuils_unknown']:.3f}"),
        ("découplage statique du banc", not violations, f"{len(violations)} violation(s)"),
        ("ajustements journalisés dans une chaîne Γ intègre", journal_ok, ""),
    ]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python3 -m omega_hermes.loop")
    ap.add_argument("--graine", type=int, default=GRAINE)
    ap.add_argument("--iterations", type=int, default=5)
    ap.add_argument("--scenarios", type=int, default=200)
    ap.add_argument("--entrainement", type=int, default=150, help="échantillons par classe")
    ap.add_argument("--journal", help="chaîne Γ des ajustements (défaut : dossier temporaire)")
    ap.add_argument("--evidence", default=os.path.join(os.path.dirname(__file__),
                                                       "hermes_evidence.json"))
    a = ap.parse_args(argv)

    with tempfile.TemporaryDirectory() as tmp:
        chemin_journal = a.journal or os.path.join(tmp, "loop_audit.jsonl")
        res = boucle(a.graine, a.iterations, a.scenarios, a.entrainement, Chaine(chemin_journal))
        rapport_journal = verifier_chaine(chemin_journal)
    viol = decouplage.violations()
    g = res["global"]
    print(f"HERMÈS — graine {a.graine}, boucle {a.scenarios} × {a.iterations}, "
          f"entraînement {a.entrainement} par classe")
    for it in res["iterations"]:
        print(f"  itération {it['iteration']} : score {it['score']:.4f}  BER {it['ber']:.3f}  "
              f"FPR {it['fpr']:.3f}  FNR {it['fnr']:.3f}  seuil strict {it['seuil_strict']:.1f}")
    for aj in res["ajustements"]:
        print(f"  ajustement {aj['iteration']} : {aj['action']} ({aj['raison']}) "
              f"{aj['seuil_strict_avant']:.1f} → {aj['seuil_strict_apres']:.1f}")
    c = g["composantes"]
    print(f"Global : score {g['score']:.4f} = 0,4 × {c['1-BER']:.3f} + 0,4 × {c['rejet_inconnu']:.3f}"
          f" + 0,2 × {c['1-FPR']:.3f}")
    print(f"  rejets inconnu / COVERT / DRAFT : {g['rejet_inconnu']:.3f} / "
          f"{g['covert_rejection']:.3f} / {g['draft_rejection']:.3f}   FPR {g['fpr']:.3f}   "
          f"BER {g['ber']:.3f}   FNR {g['fnr']:.3f}")
    print(f"  exactitude sur 7 labels : {g['exactitude_7_labels']:.3f} (chute mécanique attendue, §4.4)")
    print(f"  latence médiane {g['latence_mediane_ms']:.3f} ms (plancher "
          f"{g['latence_plancher_ms'] * 1e3:.2f} µs soustrait)")
    print("Bandes de distance (min · médiane · max) :")
    for k, b in res["bandes_distance"].items():
        print(f"  {k:20s} {b['min']:10.1f} · {b['mediane']:10.1f} · {b['max']:10.1f}")
    print()
    liste = criteres(res, viol, rapport_journal.integre and rapport_journal.blocs == a.iterations)
    for nom, ok, detail in liste:
        print(f"[{'OK' if ok else 'ÉCHEC'}] {nom}" + (f" — {detail}" if detail else ""))
    reussis = sum(ok for _, ok, _ in liste)
    verdict = "OK" if reussis == len(liste) else "ECHEC"
    print(f"\n{reussis}/{len(liste)} critères — {'TOUT EST OK' if verdict == 'OK' else 'ÉCHEC'}")
    ecrire(a.evidence, module="omega_hermes", phase=2, etiquette="SIMULÉ", verdict=verdict,
           graine=a.graine,
           config={"iterations": a.iterations, "scenarios": a.scenarios,
                   "entrainement_par_classe": a.entrainement, "cible_fnr": CIBLE_FNR,
                   "pas": {"resserrer": PAS_RESSERRER, "relacher": PAS_RELACHER},
                   "bornes_seuil_strict": BORNES_STRICT},
           mesures=res | {"criteres": [{"critere": n, "ok": ok, "detail": d} for n, ok, d in liste],
                          "decouplage": {"violations": viol},
                          "journal": {"integre": rapport_journal.integre,
                                      "blocs": rapport_journal.blocs}},
           limites=["Données synthétiques uniquement : ces mesures ne prouvent rien sur un signal réel.",
                    "Les paramètres du jumeau et d'ALICE ont été réglés pour que les familles soient "
                    "séparables ; BOB est mesuré sur ce monde-là.",
                    "FPR lu comme « anomalie acceptée comme connue » et entraînement lu comme "
                    "« par classe » : deux interprétations du blueprint à confirmer.",
                    "COVERT et DRAFT sont rejetés, jamais nommés : ils n'existent pas à l'entraînement.",
                    "La boucle s'ajuste avec les labels d'ALICE : c'est un banc, pas un apprentissage en ligne.",
                    "Ω Q non calculé (phase 5) : le module n'est pas « terminé » au sens du §11.4."])
    return 0 if verdict == "OK" else 1


if __name__ == "__main__":
    sys.exit(main())
