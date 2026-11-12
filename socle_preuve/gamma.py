"""Chaîne Γ : journal JSON Lines append-only, chaîné par SHA-256 (blueprint §3.1).

hash = SHA-256(prev_hash || JSON canonique du bloc sans le champ hash)

Propriété [DÉMONTRÉ] : quelqu'un qui réécrit un bloc *et recalcule* la suite
obtient une chaîne localement cohérente. Seul le témoin (temoin.py) le détecte.
"""

import datetime
import fcntl
import hashlib
import json
import os
import threading
from dataclasses import dataclass
from typing import Callable

GENESE = "0" * 64
CHAMPS = ("seq", "ts", "type", "decision", "raison", "prev_hash", "hash")


def canonique(bloc: dict) -> bytes:
    corps = {k: v for k, v in bloc.items() if k != "hash"}
    return json.dumps(corps, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8")


def calculer_hash(bloc: dict) -> str:
    return hashlib.sha256(bloc["prev_hash"].encode("ascii") + canonique(bloc)).hexdigest()


def horodatage_utc() -> str:
    return (datetime.datetime.now(datetime.timezone.utc)
            .isoformat(timespec="microseconds").replace("+00:00", "Z"))


@dataclass(frozen=True)
class Rapport:
    integre: bool
    blocs: int                 # blocs valides lus avant la première faute
    tete: str                  # hash du dernier bloc valide
    seq_fautif: int | None = None
    raison: str | None = None  # identifiant stable

    def __str__(self) -> str:
        if self.integre:
            return f"INTÈGRE — {self.blocs} bloc(s), tête {self.tete[:16]}…"
        return f"ROMPUE — seq {self.seq_fautif} : {self.raison}"


def lire_blocs(chemin) -> tuple[list[dict], Rapport]:
    """Lit et vérifie toute la chaîne depuis le bloc 0."""
    blocs, prev = [], GENESE
    with open(chemin, "rb") as fh:
        donnees = fh.read()
    lignes = donnees.split(b"\n")
    if lignes and lignes[-1] == b"":
        lignes.pop()
    for attendu, brut in enumerate(lignes):
        def faute(raison, *, _blocs=blocs, _prev=prev, _attendu=attendu):
            return _blocs, Rapport(False, len(_blocs), _prev, _attendu, raison)
        try:
            bloc = json.loads(brut)
        except (UnicodeDecodeError, json.JSONDecodeError):
            return faute("json_invalide")
        if not isinstance(bloc, dict) or any(c not in bloc for c in CHAMPS):
            return faute("champ_manquant")
        if bloc["seq"] != attendu or type(bloc["seq"]) is not int:
            return faute("seq_inattendu")
        if bloc["prev_hash"] != prev:
            return faute("prev_hash_rompu")
        try:
            if calculer_hash(bloc) != bloc["hash"]:
                return faute("hash_invalide")
        except (UnicodeEncodeError, AttributeError, TypeError):
            return faute("hash_invalide")
        blocs.append(bloc)
        prev = bloc["hash"]
    return blocs, Rapport(True, len(blocs), prev)


def verifier_chaine(chemin) -> Rapport:
    return lire_blocs(chemin)[1]


class ChaineRompue(ValueError):
    def __init__(self, rapport: Rapport):
        super().__init__(str(rapport))
        self.rapport = rapport


class TeteObsolete(Exception):
    """La tête a avancé entre la lecture de l'écrivain et son écriture (OCC)."""

    def __init__(self, attendue: str, actuelle: str):
        super().__init__(f"tête attendue {attendue[:16]}…, actuelle {actuelle[:16]}…")
        self.attendue, self.actuelle = attendue, actuelle


def ouvrir_600(chemin) -> int:
    """Ouvre en ajout, crée en mode 600 et resserre un fichier existant trop ouvert."""
    fd = os.open(chemin, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
    os.fchmod(fd, 0o600)
    return fd


class Chaine:
    """Écrivain de chaîne Γ. Sûr entre threads (verrou) et entre processus (flock)."""

    def __init__(self, chemin, *, horloge: Callable[[], str] = horodatage_utc,
                 temoin=None):
        self.chemin = os.fspath(chemin)
        self._horloge = horloge
        self.temoin = temoin
        self._verrou = threading.Lock()
        os.close(ouvrir_600(self.chemin))
        rapport = verifier_chaine(self.chemin)
        if not rapport.integre:
            raise ChaineRompue(rapport)

    def inscrire(self, type: str, decision: str, raison: str,
                 donnees: dict | None = None, *, si_tete: str | None = None) -> dict:
        """Ajoute un bloc. Avec `si_tete`, n'écrit que si la tête vaut encore cette
        valeur : le contrôle OCC se fait sous le verrou d'écriture, pas au-dessus."""
        for nom, val in (("type", type), ("decision", decision), ("raison", raison)):
            if not isinstance(val, str) or not val:
                raise ValueError(f"{nom} doit être une chaîne non vide")
        with self._verrou:
            fd = ouvrir_600(self.chemin)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX)
                blocs, rapport = lire_blocs(self.chemin)
                if not rapport.integre:
                    raise ChaineRompue(rapport)
                if si_tete is not None and si_tete != rapport.tete:
                    raise TeteObsolete(si_tete, rapport.tete)
                bloc = {"seq": len(blocs), "ts": self._horloge(), "type": type,
                        "decision": decision, "raison": raison, "prev_hash": rapport.tete}
                if donnees is not None:
                    bloc["donnees"] = donnees
                bloc["hash"] = calculer_hash(bloc)
                ligne = json.dumps(bloc, sort_keys=True, separators=(",", ":"),
                                   ensure_ascii=False).encode("utf-8") + b"\n"
                os.write(fd, ligne)
                os.fsync(fd)
                if self.temoin is not None:
                    self.temoin.attester(bloc)
            finally:
                os.close(fd)  # libère aussi le flock
        return bloc
