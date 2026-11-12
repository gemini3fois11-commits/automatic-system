"""Transport scellé : la nouveauté revendiquée par le projet n'est ni le Morse, ni la radio,
ni Bell 202 (1976), c'est le **sceau vérifiable par un témoin** sur ce transport (§8.2).

Côté émission : enveloppe {seq, ts, texte}, encode en CRC-16/X-25, module AFSK.
Côté réception : démodule, décode, vérifie que `seq` croît strictement, inscrit dans Γ
avec témoin. Tout rejet (CRC, JSON, séquence, texte vide) porte un code stable.
"""

import datetime
import json

from socle_preuve.gamma import Chaine
from telegraphe.afsk import ErreurTrame, demoduler, moduler


MAX_TEXTE = 256


def _ts() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def envelopper(seq: int, texte: str, *, ts: str | None = None) -> bytes:
    """Enveloppe JSON canonique signée implicitement par le CRC-16/X-25 de la trame."""
    if not isinstance(texte, str) or not texte or len(texte) > MAX_TEXTE:
        raise ValueError("texte_invalide")
    if not isinstance(seq, int) or seq < 0:
        raise ValueError("seq_invalide")
    enveloppe = {"seq": seq, "ts": ts or _ts(), "texte": texte}
    return json.dumps(enveloppe, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def emettre(seq: int, texte: str) -> list[float]:
    """Message → trame AFSK Bell 202 modulée (échantillons [-1, 1])."""
    return moduler(envelopper(seq, texte))


class Recepteur:
    """Démodule, décode, contrôle l'ordre et scelle. `seq` doit croître strictement."""

    def __init__(self, journal: Chaine):
        self.journal = journal
        self._dernier_seq = -1
        self._init_depuis_journal()

    def _init_depuis_journal(self):
        from socle_preuve.gamma import lire_blocs
        blocs, _ = lire_blocs(self.journal.chemin)
        for b in reversed(blocs):
            if b["type"] == "telegraphe" and b["decision"] == "ACCEPTE" and "seq" in b.get("donnees", {}):
                self._dernier_seq = b["donnees"]["seq"]
                return

    def recevoir(self, echantillons) -> dict:
        try:
            charge = demoduler(echantillons)
        except ErreurTrame as e:
            return self._refuser(e.code, {})
        try:
            enveloppe = json.loads(charge)
            if not isinstance(enveloppe, dict):
                raise ValueError
            seq = enveloppe["seq"]; ts = enveloppe["ts"]; texte = enveloppe["texte"]
            if (type(seq) is not int or seq < 0 or not isinstance(ts, str)
                    or not isinstance(texte, str) or not texte or len(texte) > MAX_TEXTE):
                raise ValueError
        except (ValueError, KeyError, UnicodeDecodeError):
            return self._refuser("enveloppe_malformee", {"octets": len(charge)})
        if seq <= self._dernier_seq:
            return self._refuser("seq_non_croissant",
                                 {"seq": seq, "dernier": self._dernier_seq, "texte_sha256_prefix": _sha_prefix(texte)})
        self._dernier_seq = seq
        bloc = self.journal.inscrire("telegraphe", "ACCEPTE", "trame_scellee",
                                     {"seq": seq, "ts": ts, "texte": texte})
        return {"accepte": True, "seq": seq, "hash": bloc["hash"]}

    def _refuser(self, code: str, donnees: dict) -> dict:
        self.journal.inscrire("telegraphe", "REJETE", code, donnees)
        return {"accepte": False, "code": code}


def _sha_prefix(texte: str, n: int = 16) -> str:
    import hashlib
    return hashlib.sha256(texte.encode()).hexdigest()[:n]
