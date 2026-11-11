"""HERMÈS — mesure des décisions de BOB (blueprint §4.2, §4.3).

Définitions retenues (à confirmer, voir README) :
- « positif » = accepté comme classe connue ;
- FPR = part des anomalies (ARTIFACT, UNKNOWN, COVERT, DRAFT) acceptées comme connues ;
- FNR = part des signaux connus rejetés ;
- BER = taux d'erreur sur les labels nommables (classes connues, ARTIFACT, UNKNOWN).
  COVERT et DRAFT n'y entrent pas : BOB ne les a jamais vus, il ne peut que les rejeter ;
- score = 0,4 × (1 − BER) + 0,4 × rejet_inconnu + 0,2 × (1 − FPR), composantes toujours publiées.
"""

import numpy as np

from omega_hermes.alice import ARTIFACT, COVERT, DRAFT, LABELS, UNKNOWN
from omega_hermes.twin import CLASSES

POIDS = {"1-BER": 0.4, "rejet_inconnu": 0.4, "1-FPR": 0.2}
NOMMABLES = CLASSES + (ARTIFACT, UNKNOWN)


def _moyenne(masque_valeurs) -> float | None:
    return float(masque_valeurs.mean()) if masque_valeurs.size else None


def mesurer(labels, decisions, latences_ms=None) -> dict:
    labels, decisions = np.asarray(labels), np.asarray(decisions)
    accepte = np.isin(decisions, CLASSES)
    connu = np.isin(labels, CLASSES)
    nommable = np.isin(labels, NOMMABLES)
    ber = _moyenne(decisions[nommable] != labels[nommable])
    fpr = _moyenne(accepte[~connu])
    rejet = {lab: _moyenne(~accepte[labels == lab]) for lab in (UNKNOWN, COVERT, DRAFT, ARTIFACT)}
    par_label = {}
    for lab in LABELS:
        support = int((labels == lab).sum())
        predit = int((decisions == lab).sum())
        vrai = int(((labels == lab) & (decisions == lab)).sum())
        par_label[lab] = {"support": support, "rappel": vrai / support if support else None,
                          "precision": vrai / predit if predit else None}
    composantes = {"1-BER": 1 - ber, "rejet_inconnu": rejet[UNKNOWN], "1-FPR": 1 - fpr}
    resultat = {
        "n": int(len(labels)),
        "score": sum(POIDS[k] * composantes[k] for k in POIDS),
        "poids": POIDS,
        "composantes": composantes,
        "ber": ber, "fpr": fpr, "fnr": _moyenne(~accepte[connu]),
        "rejet_inconnu": rejet[UNKNOWN], "covert_rejection": rejet[COVERT],
        "draft_rejection": rejet[DRAFT], "artifact_rejection": rejet[ARTIFACT],
        "exactitude_7_labels": _moyenne(decisions == labels),
        "par_label": par_label,
    }
    if latences_ms is not None:
        resultat["latence_mediane_ms"] = float(np.median(latences_ms))
    return resultat
