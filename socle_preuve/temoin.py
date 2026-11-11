"""Témoin indépendant de la chaîne Γ (blueprint §3.2).

Le témoin scelle (seq, hash) de chaque bloc avec un secret qu'il est seul à
détenir : HMAC-SHA256, ou Ed25519 dont le vérificateur n'a que la clé publique
épinglée. Réécrire le journal et recalculer les SHA-256 ne reproduit pas les
sceaux : la réécriture est détectée bloc par bloc.

Limite [DÉMONTRÉ] : si le secret vit sur la même machine que le journal, qui
contrôle la machine contrôle les deux. Et une troncature *cohérente* du journal
et du fichier du témoin n'est pas détectable sans ancre de tête externe.
"""

import fcntl
import hmac
import hashlib
import json
import os
from dataclasses import dataclass, field

from socle_preuve import ed25519
from socle_preuve.gamma import Rapport, lire_blocs, ouvrir_600

DOMAINE = b"omega-gamma-temoin-v1"


def message(seq: int, h: str) -> bytes:
    return DOMAINE + b"|" + str(seq).encode() + b"|" + h.encode("ascii")


class ScelleurHMAC:
    alg = "HMAC-SHA256"

    def __init__(self, secret: bytes):
        if len(secret) < 32:
            raise ValueError("secret HMAC trop court (32 octets minimum)")
        self._secret = secret

    def sceller(self, msg: bytes) -> str:
        return hmac.new(self._secret, msg, hashlib.sha256).hexdigest()

    def verifier(self, msg: bytes, sceau: str) -> bool:
        return hmac.compare_digest(self.sceller(msg), sceau)


class ScelleurEd25519:
    alg = "Ed25519"

    def __init__(self, graine: bytes):
        self._graine = graine
        self.publique = ed25519.cle_publique(graine)

    def sceller(self, msg: bytes) -> str:
        return ed25519.signer(self._graine, msg).hex()

    def verifier(self, msg: bytes, sceau: str) -> bool:
        return VerificateurEd25519(self.publique).verifier(msg, sceau)


class VerificateurEd25519:
    """Ne détient que la clé publique épinglée : peut vérifier, jamais sceller."""
    alg = "Ed25519"

    def __init__(self, publique: bytes):
        if len(publique) != 32:
            raise ValueError("clé publique Ed25519 : 32 octets")
        self.publique = publique

    def verifier(self, msg: bytes, sceau: str) -> bool:
        try:
            sig = bytes.fromhex(sceau)
        except (ValueError, TypeError):
            return False
        return ed25519.verifier(self.publique, msg, sig)


class Temoin:
    def __init__(self, chemin, scelleur):
        self.chemin = os.fspath(chemin)
        self.scelleur = scelleur
        os.close(ouvrir_600(self.chemin))

    def attester(self, bloc: dict) -> dict:
        rec = {"seq": bloc["seq"], "hash": bloc["hash"], "alg": self.scelleur.alg,
               "sceau": self.scelleur.sceller(message(bloc["seq"], bloc["hash"]))}
        fd = ouvrir_600(self.chemin)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            os.write(fd, json.dumps(rec, sort_keys=True).encode() + b"\n")
            os.fsync(fd)
        finally:
            os.close(fd)
        return rec


@dataclass(frozen=True)
class RapportTemoin:
    chaine: Rapport
    accord: bool
    seq_fautif: int | None = None
    raison: str | None = None              # identifiant stable
    seqs_en_desaccord: tuple[int, ...] = field(default=())

    def __str__(self) -> str:
        if not self.chaine.integre:
            return str(self.chaine)
        if self.accord:
            return f"{self.chaine} — témoin en accord sur {self.chaine.blocs} bloc(s)"
        s = f"TÉMOIN EN DÉSACCORD — seq {self.seq_fautif} : {self.raison}"
        if len(self.seqs_en_desaccord) > 1:
            s += f" (blocs {', '.join(map(str, self.seqs_en_desaccord))})"
        return s


def verifier_temoin(journal, chemin_temoin, verificateur) -> RapportTemoin:
    blocs, rapport = lire_blocs(journal)
    if not rapport.integre:
        return RapportTemoin(rapport, False, rapport.seq_fautif, "chaine_rompue")

    fautes: dict[int, str] = {}

    def noter(seq, raison):
        fautes.setdefault(seq, raison)

    vus: set[int] = set()
    with open(chemin_temoin, "rb") as fh:
        lignes = [l for l in fh.read().split(b"\n") if l]
    for i, brut in enumerate(lignes):
        # Une ligne illisible est rapportée à son rang, qui vaut le seq en régime normal.
        try:
            rec = json.loads(brut)
            seq, h, alg, sceau = rec["seq"], rec["hash"], rec["alg"], rec["sceau"]
            if (type(seq) is not int or seq < 0
                    or not isinstance(h, str) or not isinstance(sceau, str)):
                raise ValueError
            msg = message(seq, h)
        except (ValueError, KeyError, TypeError, UnicodeEncodeError):
            noter(i, "temoin_illisible")
            continue
        if seq in vus:
            noter(seq, "temoin_incoherent")
            continue
        vus.add(seq)
        if alg != verificateur.alg or not verificateur.verifier(msg, sceau):
            noter(seq, "sceau_invalide")
        elif seq >= len(blocs):
            noter(seq, "temoin_orphelin")       # journal tronqué
        elif blocs[seq]["hash"] != h:
            noter(seq, "desaccord_temoin")      # bloc réécrit
    for seq in range(len(blocs)):
        if seq not in vus:
            noter(seq, "bloc_non_temoigne")

    if not fautes:
        return RapportTemoin(rapport, True)
    premier = min(fautes)
    return RapportTemoin(rapport, False, premier, fautes[premier], tuple(sorted(fautes)))
