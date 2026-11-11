"""Matrice de scénarios du banc CRYOLOOP [SIMULÉ] : un scénario par voie de décision.

Chaque scénario part d'une archive nominale synthétique, lui applique une
altération, puis vérifie la décision, le code attendu et les invariants CL-I1…CL-I5.
"""

import json
import os
import shutil
import tempfile

from cryoloop.banc import construire, ecrire_manifeste, lire_manifeste, signer
from cryoloop.validateur import SIGNATURE, Perimetre, candidat, valider
from socle_preuve import ed25519
from socle_preuve.gamma import Chaine

CLE = bytes(range(32))           # clé de test du banc, publique par construction
AUTRE_CLE = bytes(range(1, 33))
INTEGRITE = {"hash_divergent", "chaine_rompue", "signature_manifeste_invalide", "entrees_modifiees",
             "lien_symbolique", "gamma_rompu", "manifeste_illisible"}


def _json(d, rel):
    with open(os.path.join(d, rel), encoding="utf-8") as fh:
        return json.load(fh)


def _ecrire(d, rel, obj):
    with open(os.path.join(d, rel), "w", encoding="utf-8") as fh:
        json.dump(obj, fh, separators=(",", ":"))


def _modifier_ekf(d, ident, f):
    rel = f"ekf/EKF_Matrix_State_{ident}.json"
    doc = _json(d, rel)
    f(doc)
    _ecrire(d, rel, doc)
    ecrire_manifeste(d, lire_manifeste(d), CLE, redeclarer=[rel])


def _branche_s50(d, declarer):
    e09 = _json(d, "evenements/E09.json")
    rel = "evenements/E09b.json"
    _ecrire(d, rel, dict(e09, id="E09b", mesures="mesures/E09.json", note="version concurrente"))
    if declarer:
        ecrire_manifeste(d, lire_manifeste(d), CLE, redeclarer=[rel])


def _retirer_dernier(d):
    m = lire_manifeste(d)
    for rel in ("evenements/E21.json", "ekf/EKF_Matrix_State_E21.json", "mesures/E21.json"):
        os.remove(os.path.join(d, rel))
        del m["fichiers"][rel]
    ecrire_manifeste(d, m, CLE)


def _retirer_mesures(d):
    m = lire_manifeste(d)
    os.remove(os.path.join(d, "mesures/E07.json"))
    del m["fichiers"]["mesures/E07.json"]
    ecrire_manifeste(d, m, CLE)


def _champ_manifeste(d, cle, valeur):
    m = lire_manifeste(d)
    m[cle] = valeur
    ecrire_manifeste(d, m, CLE)


def _rompre_maillon(d):
    rel = "evenements/E10.json"
    ev = _json(d, rel)
    ev["prev"] = "f" * 64
    _ecrire(d, rel, ev)
    ecrire_manifeste(d, lire_manifeste(d), CLE, redeclarer=[rel])


def _alterer_mesures(d):
    with open(os.path.join(d, "mesures/E05.json"), "a") as fh:
        fh.write(" ")


def _signature_etrangere(d):
    signer(d, AUTRE_CLE)


def _P_negative(doc):
    doc["P_post"] = [[-v for v in ligne] for ligne in doc["P_post"]]


def _P_decalee(doc):
    doc["P_post"][0][0] *= 1.01


def _sans_mise_a_jour(doc):
    for k in ("P_prior", "H", "R", "K"):
        del doc[k]


def _lien(d):
    os.symlink("/etc/hostname", os.path.join(d, "mesures/lien"))


# (nom, altération, décision attendue, code attendu, crochet pendant le cycle)
SCENARIOS = [
    ("nominal", None, "ACCEPT", None, None),
    ("archive absente", "absente", "PENDING", "entrees_absentes", None),
    ("manifeste non signé", lambda d: os.remove(os.path.join(d, SIGNATURE)),
     "PENDING", "provenance_non_authentifiee", None),
    ("manifeste signé par une autre clé", _signature_etrangere,
     "QUARANTINE", "signature_manifeste_invalide", None),
    ("fichier altéré après scellement (P2)", _alterer_mesures, "QUARANTINE", "hash_divergent", None),
    ("maillon rompu, pourtant déclaré (P3)", _rompre_maillon, "QUARANTINE", "chaine_rompue", None),
    ("contradiction S50 résolue par provenance (P0)", lambda d: _branche_s50(d, False),
     "ACCEPT", None, None),
    ("contradiction S50 déclarée deux fois (P0)", lambda d: _branche_s50(d, True),
     "PENDING", "contradiction_non_resolue", None),
    ("20 événements au lieu de 21 (P1)", _retirer_dernier, "PENDING", "nombre_evenements", None),
    ("EKF : P_post non positive (P4)", lambda d: _modifier_ekf(d, "E12", _P_negative),
     "REJECT", "ekf_invalide", None),
    ("EKF : recalcul divergent (P4)", lambda d: _modifier_ekf(d, "E15", _P_decalee),
     "REJECT", "ekf_recalcul_divergent", None),
    ("EKF : mise à jour absente (P4)", lambda d: _modifier_ekf(d, "E03", _sans_mise_a_jour),
     "PENDING", "ekf_non_recalculable", None),
    ("mesures mémoire / thermique absentes (P5)", _retirer_mesures, "PENDING", "mesures_absentes", None),
    ("expected_state_hash périmé (CL-I4)", lambda d: _champ_manifeste(d, "expected_state_hash", "a" * 64),
     "REJECT", "etat_perime", None),
    ("périmètre DON-DC02 au lieu de DON-DC01", lambda d: _champ_manifeste(d, "perimetre", "DON-DC02"),
     "REJECT", "perimetre_different", None),
    ("cumul : altération + état périmé", lambda d: (_champ_manifeste(d, "expected_state_hash", "a" * 64),
                                                    _alterer_mesures(d)),
     "QUARANTINE", "hash_divergent", None),
    ("lien symbolique dans l'archive", _lien, "QUARANTINE", "lien_symbolique", None),
    ("archive modifiée pendant le cycle", None, "QUARANTINE", "entrees_modifiees", "modifier"),
]


def invariants(r, gamma_avant_octets, gamma_apres_octets) -> dict[str, bool]:
    codes = set(r.codes)
    return {
        "CL-I1": gamma_avant_octets == gamma_apres_octets or r.decision == "ACCEPT",
        "CL-I2": r.decision != "PENDING" or gamma_avant_octets == gamma_apres_octets,
        "CL-I3": not (codes & {"hash_divergent", "chaine_rompue"}) or r.decision == "QUARANTINE",
        "CL-I4": ("etat_perime" not in codes or r.decision == "REJECT"
                  or bool(codes & INTEGRITE)),
        "CL-I5": gamma_avant_octets == gamma_apres_octets,
    }


def jouer(nom, alteration, attendu, code, crochet) -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        gamma = os.path.join(tmp, "gamma.jsonl")
        ch = Chaine(gamma)
        ch.inscrire("genese", "OUVERT", "ouverture_registre", {"ledger_id": "DON-DC01"})
        base = ch.inscrire("evenement", "ACCEPTE", "invariants_ok", {"epoque": 17})["hash"]
        archive = os.path.join(tmp, "archive")
        construire(archive, base=base, cle=CLE)
        if alteration == "absente":
            shutil.rmtree(archive)
        elif alteration is not None:
            alteration(archive)
        pendant = None
        if crochet == "modifier":
            pendant = lambda: _alterer_mesures(archive)
        with open(gamma, "rb") as fh:
            avant = fh.read()
        r = valider(archive, gamma=gamma, cle_publique=ed25519.cle_publique(CLE), pendant=pendant)
        with open(gamma, "rb") as fh:
            apres = fh.read()
        cand = None
        if r.decision == "ACCEPT":
            cand = candidat(r, Perimetre())
    inv = invariants(r, avant, apres)
    ok = (r.decision == attendu and (code is None and not r.constats or code in r.codes)
          and all(inv.values()))
    return {"scenario": nom, "decision_attendue": attendu, "decision": r.decision,
            "code_attendu": code, "codes": r.codes, "isolees": r.isolees,
            "resolutions": r.resolutions, "evenements_chaines": len(r.chaine),
            "candidat": cand is not None, "invariants": inv, "ok": ok}


def tout_jouer() -> list[dict]:
    return [jouer(*s) for s in SCENARIOS]
