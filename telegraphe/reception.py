"""Télégraphe qui refuse — gardien de réception (blueprint §8.2, évolution approuvée).

Applique la doctrine de BOB (« refuser avant de croire », §4.3) à la réception,
non au signal : BOB classe des signaux par distance de Mahalanobis ; ici on juge
des messages. Deux portes, trois verdicts, chaque verdict scellé.

Portes
  1. Intégrité — la trame passe le CRC-16/X-25 (sinon ce n'est pas un message).
  2. Identité — le message porte un émetteur de l'allowlist et une étiquette
     d'authentification HMAC valide, non rejouée.

Verdicts (mappés sur les trois sorties de BOB : connu / ARTIFACT / UNKNOWN)
  - ACCEPTE    : émetteur connu, authentifié, frais.            (≈ classe connue)
  - QUARANTAINE: reçu mais douteux, mis de côté AVEC RAISON     (≈ ARTIFACT)
                 écrite, jamais livré en silence : émetteur inconnu,
                 authentification invalide, ou rejeu.
  - REFUSE     : ce n'est pas un message — CRC rompu ou format  (≈ rejet net)
                 illisible.

Chaque verdict, refus et quarantaine compris, est inscrit dans une chaîne Γ
témoignée : le gardien prouve ses refus (§1.2). Ce que le gardien NE fait pas :
il n'authentifie pas le contenu d'un émetteur légitime compromis, et son secret
partagé vit sur la machine (mêmes limites que §3.2). L'allowlist est exacte,
sans joker, comme GARDIEN.
"""

import hmac
import hashlib
import os

from socle_preuve.gamma import Chaine
from socle_preuve.temoin import ScelleurHMAC, Temoin
from telegraphe import afsk, trame

ACCEPTE, QUARANTAINE, REFUSE = "ACCEPTE", "QUARANTAINE", "REFUSE"
SEP = b"\x1f"                      # séparateur d'unité, hors de l'alphabet télégraphe
DOMAINE = b"omega-telegraphe-reception-v1"


def _tag(cle: bytes, indicatif: str, seq: int, texte: str) -> str:
    msg = DOMAINE + SEP + indicatif.encode() + SEP + str(seq).encode() + SEP + texte.encode("utf-8")
    return hmac.new(cle, msg, hashlib.sha256).hexdigest()


def construire_message(indicatif: str, seq: int, texte: str, cle: bytes) -> list[int]:
    """Côté émetteur : trame authentifiée prête à moduler (indicatif, seq, HMAC, texte)."""
    if SEP in indicatif.encode() or SEP in texte.encode("utf-8"):
        raise ValueError("séparateur 0x1f interdit dans l'indicatif ou le texte")
    tag = _tag(cle, indicatif, seq, texte)
    charge = SEP.join([indicatif.encode(), str(seq).encode(), tag.encode(), texte.encode("utf-8")])
    return trame.construire(charge)


class Verdict:
    __slots__ = ("decision", "raison", "indicatif", "seq", "texte", "bloc")

    def __init__(self, decision, raison, indicatif=None, seq=None, texte=None, bloc=None):
        self.decision, self.raison = decision, raison
        self.indicatif, self.seq, self.texte, self.bloc = indicatif, seq, texte, bloc

    def __repr__(self):
        d = f" {self.indicatif}#{self.seq}" if self.indicatif else ""
        return f"{self.decision}({self.raison}){d}"


class GardienReception:
    """Allowlist exacte indicatif→clé ; chaque verdict scellé dans une chaîne Γ témoignée."""

    def __init__(self, allowlist: dict[str, bytes], chemin_journal, chemin_temoin,
                 scelleur, *, horloge=None):
        self.allowlist = dict(allowlist)
        self.temoin = Temoin(os.fspath(chemin_temoin), scelleur)
        kwargs = {"temoin": self.temoin}
        if horloge is not None:
            kwargs["horloge"] = horloge
        self.chaine = Chaine(os.fspath(chemin_journal), **kwargs)
        self._vus: set[tuple[str, int]] = set()      # (indicatif, seq) déjà acceptés : anti-rejeu

    def _sceller(self, decision, raison, donnees) -> dict:
        return self.chaine.inscrire("reception", decision, raison, donnees)

    def recevoir(self, bits: list[int]) -> Verdict:
        """Juge une trame reçue (bits démodulés) et scelle le verdict.

        Raisons stables : crc_invalide, format_invalide, emetteur_inconnu,
        authentification_invalide, rejeu, authentifie.
        """
        # Porte 1 — intégrité.
        try:
            charge = trame.analyser(bits)
        except trame.TrameInvalide as ex:
            bloc = self._sceller(REFUSE, "crc_invalide" if ex.raison == "crc_invalide" else ex.raison,
                                 {"porte": "integrite", "raison_trame": ex.raison})
            return Verdict(REFUSE, "crc_invalide" if ex.raison == "crc_invalide" else ex.raison, bloc=bloc)

        parts = charge.split(SEP, 3)
        if len(parts) != 4:
            bloc = self._sceller(REFUSE, "format_invalide", {"porte": "integrite", "champs": len(parts)})
            return Verdict(REFUSE, "format_invalide", bloc=bloc)
        try:
            indicatif = parts[0].decode()
            seq = int(parts[1])
            tag = parts[2].decode()
            texte = parts[3].decode("utf-8")
        except (ValueError, UnicodeDecodeError):
            bloc = self._sceller(REFUSE, "format_invalide", {"porte": "integrite"})
            return Verdict(REFUSE, "format_invalide", bloc=bloc)

        base = {"indicatif": indicatif, "seq": seq, "porte": "identite"}
        # Porte 2 — identité.
        cle = self.allowlist.get(indicatif)
        if cle is None:
            bloc = self._sceller(QUARANTAINE, "emetteur_inconnu", base)
            return Verdict(QUARANTAINE, "emetteur_inconnu", indicatif, seq, texte, bloc)
        if not hmac.compare_digest(tag, _tag(cle, indicatif, seq, texte)):
            bloc = self._sceller(QUARANTAINE, "authentification_invalide", base)
            return Verdict(QUARANTAINE, "authentification_invalide", indicatif, seq, texte, bloc)
        if (indicatif, seq) in self._vus:
            bloc = self._sceller(QUARANTAINE, "rejeu", base)
            return Verdict(QUARANTAINE, "rejeu", indicatif, seq, texte, bloc)

        self._vus.add((indicatif, seq))
        bloc = self._sceller(ACCEPTE, "authentifie", {**base, "texte": texte})
        return Verdict(ACCEPTE, "authentifie", indicatif, seq, texte, bloc)

    def recevoir_signal(self, ech: list[float], n_bits: int) -> Verdict:
        """Démodule un signal AFSK puis juge la trame (chaîne de réception complète)."""
        return self.recevoir(afsk.demoduler(ech, n_bits))
