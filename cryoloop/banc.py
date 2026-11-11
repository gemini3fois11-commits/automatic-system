"""Banc d'essai CRYOLOOP : archives SYNTHÉTIQUES au format cryoloop-archive-v0.

[SIMULÉ] Ces archives sont fabriquées pour exercer le validateur. Elles ne
remplacent pas les archives DON-DC01 réelles, qui n'ont pas été fournies, et ne
disent rien de leur contenu.
"""

import hashlib
import json
import os

import numpy as np

from socle_preuve import ed25519
from socle_preuve.gamma import GENESE
from cryoloop.validateur import FORMAT, MANIFESTE, SIGNATURE, Perimetre

M_OBSERVATIONS = 8


def _ecrire(chemin, objet) -> bytes:
    octets = json.dumps(objet, separators=(",", ":")).encode()
    os.makedirs(os.path.dirname(chemin), exist_ok=True)
    with open(chemin, "wb") as fh:
        fh.write(octets)
    return octets


def _sha(octets):
    return hashlib.sha256(octets).hexdigest()


def ekf(rng, n, epoque, *, mise_a_jour=True) -> dict:
    A = rng.normal(size=(n, n))
    P_prior = A @ A.T / n + 0.1 * np.eye(n)
    H = rng.normal(size=(M_OBSERVATIONS, n)) / np.sqrt(n)
    R = np.diag(rng.uniform(0.1, 1.0, M_OBSERVATIONS))
    S = H @ P_prior @ H.T + R
    K = np.linalg.solve(S, H @ P_prior).T
    P_post = (np.eye(n) - K @ H) @ P_prior
    P_post = (P_post + P_post.T) / 2
    doc = {"epoque": epoque, "P_post": P_post.tolist()}
    if mise_a_jour:
        doc |= {"P_prior": P_prior.tolist(), "H": H.tolist(), "R": R.tolist(), "K": K.tolist()}
    return doc


# 21 époques de S18 à S100, avec la transition S50 → S51 que vise la priorité P0.
EPOQUES_DON_DC01 = (18, 22, 26, 30, 34, 38, 42, 46, 50, 51, 55, 60, 65, 70, 75, 80, 85, 90, 95, 98, 100)


def epoques(perimetre: Perimetre) -> list[int]:
    if perimetre == Perimetre():
        return list(EPOQUES_DON_DC01)
    return [int(round(e)) for e in np.linspace(perimetre.debut, perimetre.fin, perimetre.evenements)]


def construire(dossier, *, graine=7, perimetre=Perimetre(), base=GENESE,
               cle: bytes | None = None) -> bytes | None:
    """Archive nominale : chaîne complète, EKF recalculables, mesures, manifeste signé."""
    rng = np.random.default_rng(np.random.SeedSequence([graine, 42]))
    fichiers, prev = {}, GENESE
    for i, ep in enumerate(epoques(perimetre)):
        ident = f"E{i + 1:02d}"
        chemins = {"ekf": f"ekf/EKF_Matrix_State_{ident}.json", "mesures": f"mesures/{ident}.json"}
        fichiers[chemins["ekf"]] = _sha(_ecrire(os.path.join(dossier, chemins["ekf"]),
                                                ekf(rng, perimetre.dimension_ekf, ep)))
        fichiers[chemins["mesures"]] = _sha(_ecrire(
            os.path.join(dossier, chemins["mesures"]),
            {"memoire": rng.uniform(0, 1, 16).tolist(), "thermique": rng.uniform(20, 80, 16).tolist()}))
        ev = {"id": ident, "epoque": ep, "prev": prev, **chemins}
        octets = _ecrire(os.path.join(dossier, f"evenements/{ident}.json"), ev)
        fichiers[f"evenements/{ident}.json"] = prev = _sha(octets)
    manifeste = {"format": FORMAT, "perimetre": perimetre.nom,
                 "epoques": [perimetre.debut, perimetre.fin],
                 "evenements_attendus": perimetre.evenements,
                 "expected_state_hash": base, "fichiers": fichiers}
    _ecrire(os.path.join(dossier, MANIFESTE), manifeste)
    if cle is not None:
        signer(dossier, cle)
    return cle


def lire_manifeste(dossier) -> dict:
    with open(os.path.join(dossier, MANIFESTE), encoding="utf-8") as fh:
        return json.load(fh)


def ecrire_manifeste(dossier, manifeste, cle=None, *, redeclarer=()):
    """Réécrit le manifeste (en recalculant les empreintes de `redeclarer`) et le re-signe."""
    for rel in redeclarer:
        with open(os.path.join(dossier, rel), "rb") as fh:
            manifeste["fichiers"][rel] = _sha(fh.read())
    _ecrire(os.path.join(dossier, MANIFESTE), manifeste)
    if cle is not None:
        signer(dossier, cle)


def signer(dossier, cle: bytes):
    with open(os.path.join(dossier, MANIFESTE), "rb") as fh:
        sig = ed25519.signer(cle, fh.read())
    with open(os.path.join(dossier, SIGNATURE), "w") as fh:
        fh.write(sig.hex())
