"""Validateur CRYOLOOP Ω∞ — un cycle /LOOP (cryoloop/SPEC.md).

FREEZE INPUTS → NORMALIZE ARCHIVES → RECONCILE EPOCHS → VERIFY SHA-256 →
VERIFY HASH CHAIN → VALIDATE EKF → AUDIT MEMORY / THERMAL → INVARIANT GATE
→ ACCEPT (candidat Γ) · PENDING (Γ préservé) · QUARANTINE (preuve isolée) · REJECT.

Invariants du cycle, nommés CL-I1…CL-I5 pour ne pas les confondre avec
les I₁–I₅ de l'Invariant Gate de rinv :
  CL-I1  Γ_{t+1} ≠ Γ_t ⇒ ACCEPT
  CL-I2  PENDING ⇒ Γ_{t+1} = Γ_t
  CL-I3  hash recalculé ≠ hash déclaré ⇒ QUARANTINE
  CL-I4  expected_state_hash ≠ current_state_hash ⇒ REJECT
  CL-I5  Observation ≠ Autorisation : le validateur ne committe jamais Γ ;
         ACCEPT produit un candidat, rien de plus.

Le validateur est en lecture seule sur l'archive et sur Γ. Il lit l'archive une
seule fois (gel), travaille sur cette copie, puis vérifie que le disque n'a pas
bougé pendant le cycle.
"""

import hashlib
import json
import os
import stat
from dataclasses import dataclass, field

import numpy as np

from socle_preuve import ed25519
from socle_preuve.gamma import GENESE, verifier_chaine

FORMAT = "cryoloop-archive-v0"
MANIFESTE, SIGNATURE = "MANIFEST.json", "MANIFEST.sig"
TAILLE_MAX = 512 * 1024 * 1024
ETAPES = ("FREEZE INPUTS", "NORMALIZE ARCHIVES", "RECONCILE EPOCHS", "VERIFY SHA-256",
          "VERIFY HASH CHAIN", "VALIDATE EKF", "AUDIT MEMORY / THERMAL", "INVARIANT GATE")
GRAVITE = {"ACCEPT": 0, "PENDING": 1, "REJECT": 2, "QUARANTINE": 3}

# Chaque code mène à une décision. En cas de cumul, la plus grave l'emporte :
# QUARANTINE > REJECT > PENDING > ACCEPT (choix à confirmer, voir SPEC.md).
DECISION = {
    "entrees_absentes": "PENDING",
    "archive_trop_grande": "PENDING",
    "format_inconnu": "PENDING",
    "fichier_absent": "PENDING",
    "provenance_non_authentifiee": "PENDING",
    "contradiction_non_resolue": "PENDING",
    "maillon_non_declare": "PENDING",
    "nombre_evenements": "PENDING",
    "continuite_incomplete": "PENDING",
    "ekf_non_recalculable": "PENDING",
    "mesures_absentes": "PENDING",
    "perimetre_different": "REJECT",
    "evenement_malforme": "REJECT",
    "epoque_hors_perimetre": "REJECT",
    "epoques_non_croissantes": "REJECT",
    "ekf_invalide": "REJECT",
    "ekf_epoque_incoherente": "REJECT",
    "ekf_recalcul_divergent": "REJECT",
    "mesures_invalides": "REJECT",
    "etat_perime": "REJECT",
    "manifeste_illisible": "QUARANTINE",
    "signature_manifeste_invalide": "QUARANTINE",
    "lien_symbolique": "QUARANTINE",
    "hash_divergent": "QUARANTINE",
    "chaine_rompue": "QUARANTINE",
    "gamma_rompu": "QUARANTINE",
    "entrees_modifiees": "QUARANTINE",
}


@dataclass(frozen=True)
class Perimetre:
    """Fixé par l'opérateur (« Autorité : CORE »), jamais lu dans l'archive."""
    nom: str = "DON-DC01"
    debut: int = 18
    fin: int = 100
    evenements: int = 21
    dimension_ekf: int = 64


@dataclass
class Constat:
    code: str
    etape: str
    detail: str = ""
    fichier: str | None = None

    @property
    def decision(self) -> str:
        return DECISION[self.code]


@dataclass
class Rapport:
    decision: str = "ACCEPT"
    constats: list[Constat] = field(default_factory=list)
    isolees: dict[str, str] = field(default_factory=dict)       # fichier → motif
    resolutions: list[str] = field(default_factory=list)
    chaine: list[dict] = field(default_factory=list)            # événements retenus, dans l'ordre
    archive_sha256: str | None = None
    gamma_avant: str | None = None
    gamma_apres: str | None = None
    base: str | None = None
    attendu: str | None = None

    @property
    def codes(self) -> list[str]:
        return sorted({c.code for c in self.constats})

    @property
    def code_principal(self) -> str:
        if not self.constats:
            return "invariants_ok"
        pire = max(GRAVITE[c.decision] for c in self.constats)
        return next(c.code for c in self.constats if GRAVITE[c.decision] == pire)

    @property
    def gamma_preserve(self) -> bool:
        return self.gamma_avant == self.gamma_apres

    def statut(self, etape: str) -> str:
        codes = sorted({c.code for c in self.constats if c.etape == etape})
        return "OK" if not codes else ", ".join(codes)

    def en_dict(self) -> dict:
        return {"decision": self.decision, "code_principal": self.code_principal,
                "codes": self.codes,
                "etapes": {e: self.statut(e) for e in ETAPES},
                "constats": [c.__dict__ for c in self.constats],
                "isolees": self.isolees, "resolutions": self.resolutions,
                "chaine": self.chaine, "archive_sha256": self.archive_sha256,
                "base": self.base, "attendu": self.attendu,
                "gamma_avant": self.gamma_avant, "gamma_apres": self.gamma_apres,
                "gamma_preserve": self.gamma_preserve}


def _sha(octets: bytes) -> str:
    return hashlib.sha256(octets).hexdigest()


def _empreinte_fichier(chemin) -> str | None:
    try:
        with open(chemin, "rb") as fh:
            return _sha(fh.read())
    except FileNotFoundError:
        return None


def _geler(racine) -> tuple[dict[str, bytes], list[str]]:
    """Lit chaque fichier régulier une fois. Les liens symboliques ne sont pas suivis."""
    fichiers, liens, total = {}, [], 0
    for dossier, sous, noms in os.walk(racine, followlinks=False):
        for nom in sorted(noms) + [s for s in sous if os.path.islink(os.path.join(dossier, s))]:
            chemin = os.path.join(dossier, nom)
            rel = os.path.relpath(chemin, racine).replace(os.sep, "/")
            st = os.lstat(chemin)
            if stat.S_ISLNK(st.st_mode):
                liens.append(rel)
                continue
            if not stat.S_ISREG(st.st_mode):
                continue
            total += st.st_size
            if total > TAILLE_MAX:
                raise OverflowError
            with open(chemin, "rb") as fh:
                fichiers[rel] = fh.read()
    return fichiers, liens


def _json(octets: bytes):
    return json.loads(octets.decode("utf-8"))


def _matrice(valeur, forme) -> np.ndarray | None:
    try:
        M = np.asarray(valeur, dtype=float)
    except (TypeError, ValueError):
        return None
    if M.shape != forme or not np.isfinite(M).all():
        return None
    return M


def _covariance_valide(P: np.ndarray) -> bool:
    echelle = max(np.abs(P).max(), 1e-300)
    if np.abs(P - P.T).max() > 1e-8 * echelle:
        return False
    return np.linalg.eigvalsh((P + P.T) / 2).min() >= -1e-9 * echelle


def _proche(A, B) -> bool:
    return np.allclose(A, B, rtol=1e-6, atol=1e-9 * max(np.abs(B).max(), 1.0))


def valider(archive, *, gamma=None, perimetre: Perimetre = Perimetre(),
            cle_publique: bytes | None = None, pendant=None) -> Rapport:
    """Un cycle complet. `pendant` : crochet de test appelé juste après le gel."""
    r = Rapport()
    noter = lambda code, etape, detail="", fichier=None: r.constats.append(
        Constat(code, etape, detail, fichier))
    r.gamma_avant = _empreinte_fichier(gamma) if gamma else None

    def conclure() -> Rapport:
        r.gamma_apres = _empreinte_fichier(gamma) if gamma else None
        r.decision = max((c.decision for c in r.constats), key=GRAVITE.__getitem__,
                         default="ACCEPT")
        return r

    # 1. FREEZE INPUTS
    e = ETAPES[0]
    if not archive or not os.path.isdir(archive):
        noter("entrees_absentes", e, f"archive introuvable : {archive}")
        return conclure()
    try:
        gel, liens = _geler(archive)
    except OverflowError:
        noter("archive_trop_grande", e, f"plus de {TAILLE_MAX} octets")
        return conclure()
    for lien in liens:
        noter("lien_symbolique", e, "lien non suivi", lien)
        r.isolees[lien] = "lien_symbolique"
    r.archive_sha256 = _sha(json.dumps({k: _sha(v) for k, v in sorted(gel.items())},
                                       sort_keys=True).encode())
    if pendant is not None:
        pendant()

    # 2. NORMALIZE ARCHIVES
    e = ETAPES[1]
    manifeste = None
    if MANIFESTE not in gel:
        noter("fichier_absent", e, "manifeste absent", MANIFESTE)
    else:
        try:
            manifeste = _json(gel[MANIFESTE])
            if not isinstance(manifeste, dict):
                raise ValueError
        except (ValueError, UnicodeDecodeError):
            noter("manifeste_illisible", e, "", MANIFESTE)
            manifeste = None
    if manifeste is not None and manifeste.get("format") != FORMAT:
        noter("format_inconnu", e, f"format {manifeste.get('format')!r}, attendu {FORMAT}")
        manifeste = None
    if manifeste is None:
        return conclure()
    declares = manifeste.get("fichiers")
    if not isinstance(declares, dict):
        noter("manifeste_illisible", e, "champ fichiers absent", MANIFESTE)
        return conclure()
    if (manifeste.get("perimetre") != perimetre.nom
            or manifeste.get("epoques") != [perimetre.debut, perimetre.fin]
            or manifeste.get("evenements_attendus") != perimetre.evenements):
        noter("perimetre_different", e,
              f"manifeste {manifeste.get('perimetre')} {manifeste.get('epoques')} "
              f"{manifeste.get('evenements_attendus')} ≠ opérateur {perimetre}")
    evenements = {}
    for rel, octets in gel.items():
        if not rel.startswith("evenements/"):
            continue
        try:
            ev = _json(octets)
            if (not isinstance(ev, dict) or not isinstance(ev.get("id"), str)
                    or type(ev.get("epoque")) is not int or not isinstance(ev.get("prev"), str)
                    or not isinstance(ev.get("ekf"), str) or not isinstance(ev.get("mesures"), str)):
                raise ValueError
        except (ValueError, UnicodeDecodeError):
            if rel in declares:
                noter("evenement_malforme", e, "", rel)
            r.isolees[rel] = "evenement_malforme"
            continue
        evenements[rel] = dict(ev, _fichier=rel, _sha256=_sha(octets))

    # 3. RECONCILE EPOCHS
    e = ETAPES[2]
    connus = {GENESE} | {ev["_sha256"] for ev in evenements.values()}
    successeurs: dict[str, list[dict]] = {}
    for ev in evenements.values():
        successeurs.setdefault(ev["prev"], []).append(ev)
    courant, chaine, complete = GENESE, [], True
    while courant in successeurs:
        candidats = sorted(successeurs[courant], key=lambda v: v["_fichier"])
        retenus = [c for c in candidats if c["_fichier"] in declares]
        if len(candidats) > 1:
            epoques = sorted({c["epoque"] for c in candidats})
            if len(retenus) == 1:
                for c in candidats:
                    if c is not retenus[0]:
                        r.isolees[c["_fichier"]] = "branche_non_declaree"
                r.resolutions.append(f"contradiction S{'/'.join(map(str, epoques))} résolue par "
                                     f"provenance : {retenus[0]['_fichier']} retenu")
            elif len(retenus) > 1:
                noter("contradiction_non_resolue", e,
                      f"S{'/'.join(map(str, epoques))} : {len(retenus)} branches déclarées",
                      ", ".join(c["_fichier"] for c in retenus))
                complete = False
                break
        if not retenus:
            noter("maillon_non_declare", e, "la chaîne passe par un fichier non déclaré",
                  candidats[0]["_fichier"])
            complete = False
            break
        suivant = retenus[0]
        if chaine and suivant["epoque"] <= chaine[-1]["epoque"]:
            noter("epoques_non_croissantes", e,
                  f"S{chaine[-1]['epoque']} puis S{suivant['epoque']}", suivant["_fichier"])
        if not perimetre.debut <= suivant["epoque"] <= perimetre.fin:
            noter("epoque_hors_perimetre", e, f"S{suivant['epoque']}", suivant["_fichier"])
        chaine.append(suivant)
        courant = suivant["_sha256"]
        if len(chaine) > len(evenements):
            break  # cycle impossible avec SHA-256, garde-fou
    if complete:
        if len(chaine) != perimetre.evenements:
            noter("nombre_evenements", e, f"{len(chaine)} chaînés, {perimetre.evenements} attendus")
        if not chaine or chaine[0]["epoque"] != perimetre.debut or chaine[-1]["epoque"] != perimetre.fin:
            bornes = f"S{chaine[0]['epoque']}–S{chaine[-1]['epoque']}" if chaine else "vide"
            noter("continuite_incomplete", e,
                  f"{bornes}, attendu S{perimetre.debut}–S{perimetre.fin}")
    r.chaine = [{"id": ev["id"], "epoque": ev["epoque"], "fichier": ev["_fichier"],
                 "sha256": ev["_sha256"]} for ev in chaine]

    # 4. VERIFY SHA-256 — provenance du manifeste, puis chaque fichier déclaré
    e = ETAPES[3]
    if SIGNATURE not in gel or cle_publique is None:
        noter("provenance_non_authentifiee", e,
              "signature du manifeste absente" if cle_publique else "aucune clé publique épinglée")
    else:
        try:
            sig = bytes.fromhex(gel[SIGNATURE].decode("ascii").strip())
        except (ValueError, UnicodeDecodeError):
            sig = b""
        if not ed25519.verifier(cle_publique, gel[MANIFESTE], sig):
            noter("signature_manifeste_invalide", e, "", SIGNATURE)
    verifies = set()
    for rel, declare in sorted(declares.items()):
        if rel not in gel:
            noter("fichier_absent", e, "déclaré, absent de l'archive", rel)
        elif _sha(gel[rel]) != declare:
            noter("hash_divergent", e, f"déclaré {str(declare)[:16]}…, recalculé "
                                       f"{_sha(gel[rel])[:16]}…", rel)
            r.isolees[rel] = "hash_divergent"
        else:
            verifies.add(rel)
    for rel in gel:
        if rel not in declares and rel not in (MANIFESTE, SIGNATURE) and rel not in r.isolees:
            r.isolees[rel] = "non_declare"

    # 5. VERIFY HASH CHAIN
    e = ETAPES[4]
    for rel, ev in sorted(evenements.items()):
        if rel in declares and ev["prev"] not in connus:
            noter("chaine_rompue", e, f"prev {ev['prev'][:16]}… ne correspond à aucun maillon", rel)

    # 6. VALIDATE EKF
    e = ETAPES[5]
    n = perimetre.dimension_ekf
    for ev in chaine:
        rel = ev["ekf"]
        if rel not in verifies:
            if rel not in declares:
                noter("fichier_absent", e, "EKF non déclaré", rel)
            continue
        try:
            ekf = _json(gel[rel])
            if not isinstance(ekf, dict):
                raise ValueError
        except (ValueError, UnicodeDecodeError):
            noter("ekf_invalide", e, "JSON illisible", rel)
            continue
        if ekf.get("epoque") != ev["epoque"]:
            noter("ekf_epoque_incoherente", e, f"S{ekf.get('epoque')} ≠ S{ev['epoque']}", rel)
        P_post = _matrice(ekf.get("P_post"), (n, n))
        if P_post is None or not _covariance_valide(P_post):
            noter("ekf_invalide", e, f"P_post n'est pas une covariance {n}×{n}", rel)
            continue
        if not all(k in ekf for k in ("P_prior", "H", "R", "K")):
            noter("ekf_non_recalculable", e, "P_prior, H, R ou K absent", rel)
            continue
        try:
            H0 = np.asarray(ekf["H"], dtype=float)
            m = H0.shape[0] if H0.ndim == 2 else -1
        except (TypeError, ValueError):
            m = -1
        P_prior = _matrice(ekf["P_prior"], (n, n))
        H, R, K = _matrice(ekf["H"], (m, n)), _matrice(ekf["R"], (m, m)), _matrice(ekf["K"], (n, m))
        if any(x is None for x in (P_prior, H, R, K)) or not _covariance_valide(P_prior):
            noter("ekf_invalide", e, "dimensions ou valeurs de mise à jour invalides", rel)
            continue
        try:
            S = H @ P_prior @ H.T + R
            K_calc = np.linalg.solve(S, H @ P_prior).T
        except np.linalg.LinAlgError:
            noter("ekf_invalide", e, "innovation singulière", rel)
            continue
        P_calc = (np.eye(n) - K_calc @ H) @ P_prior
        if not (_proche(K, K_calc) and _proche(P_post, P_calc)):
            ecart = float(np.abs(P_post - P_calc).max())
            noter("ekf_recalcul_divergent", e, f"écart max sur P_post {ecart:.3e}", rel)

    # 7. AUDIT MEMORY / THERMAL — présence et forme des mesures originales, sans interprétation
    e = ETAPES[6]
    for ev in chaine:
        rel = ev["mesures"]
        if rel not in declares or rel not in gel:
            noter("mesures_absentes", e, "", rel)
            continue
        if rel not in verifies:
            continue
        try:
            mes = _json(gel[rel])
            ok = isinstance(mes, dict) and all(
                isinstance(mes.get(k), list) and mes[k]
                and all(isinstance(v, (int, float)) and not isinstance(v, bool)
                        and np.isfinite(v) for v in mes[k])
                for k in ("memoire", "thermique"))
        except (ValueError, UnicodeDecodeError):
            ok = False
        if not ok:
            noter("mesures_invalides", e, "memoire et thermique : listes de nombres finis", rel)

    # 8. INVARIANT GATE — OCC (CL-I4), puis contrôle du gel
    e = ETAPES[7]
    r.base = GENESE
    if gamma and os.path.exists(gamma):
        rapport = verifier_chaine(gamma)
        if not rapport.integre:
            noter("gamma_rompu", e, str(rapport), os.path.basename(gamma))
        r.base = rapport.tete
    r.attendu = manifeste.get("expected_state_hash")
    if r.attendu != r.base:
        noter("etat_perime", e, f"attendu {str(r.attendu)[:16]}…, courant {r.base[:16]}…")
    try:
        regel, _ = _geler(archive)
    except (OverflowError, OSError):
        regel = {}
    for rel in sorted(set(gel) | set(regel)):
        if regel.get(rel) != gel.get(rel):
            quoi = "ajouté" if rel not in gel else ("supprimé" if rel not in regel else "modifié")
            noter("entrees_modifiees", ETAPES[0], f"{quoi} pendant le cycle", rel)
    return conclure()


def candidat(r: Rapport, perimetre: Perimetre) -> dict:
    """Le candidat Γ d'un ACCEPT. CL-I5 : il n'est jamais committé par le validateur."""
    if r.decision != "ACCEPT":
        raise ValueError("seul un ACCEPT produit un candidat")
    return {"format": "cryoloop-candidat-v0", "perimetre": perimetre.nom,
            "epoques": [perimetre.debut, perimetre.fin], "base": r.base,
            "archive_sha256": r.archive_sha256, "evenements": r.chaine,
            "statut": "CANDIDAT — commit Γ non effectué (CL-I5)"}
