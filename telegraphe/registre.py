"""Registre scellé des émissions du télégraphe (blueprint §8.2).

Chaque message émis est inscrit dans une chaîne Γ du socle de preuve, scellée
par un témoin (HMAC-SHA256 par défaut, ou Ed25519). On n'enregistre pas le son
— seulement le texte, les octets utiles, le CRC et la taille du signal. Le
sceau du témoin, pas le CRC, est ce qui authentifie : réécrire un message déjà
émis est détecté bloc par bloc tant que l'attaquant n'a pas le secret du témoin.

La nouveauté du télégraphe tient ici, et nulle part ailleurs : Morse (1844),
la radio (1901) et Bell 202 (1976) sont anciens ; le sceau vérifiable par un
témoin sur le transport est le seul apport revendiqué (blueprint §8.2).

Limites héritées du socle (§3.2) : si le secret du témoin vit sur la même
machine que le journal, qui tient la machine tient les deux ; une troncature
cohérente du journal et du témoin n'est pas détectable sans ancre externe.
"""

import os

from socle_preuve.gamma import Chaine, verifier_chaine
from socle_preuve.temoin import (
    ScelleurHMAC, Temoin, VerificateurEd25519, verifier_temoin,
)
from telegraphe import afsk, trame


class Registre:
    """Chaîne Γ des émissions, scellée par un témoin."""

    def __init__(self, chemin_journal, chemin_temoin, scelleur, *, horloge=None):
        self.chemin_journal = os.fspath(chemin_journal)
        self.chemin_temoin = os.fspath(chemin_temoin)
        self.temoin = Temoin(self.chemin_temoin, scelleur)
        kwargs = {"temoin": self.temoin}
        if horloge is not None:
            kwargs["horloge"] = horloge
        self.chaine = Chaine(self.chemin_journal, **kwargs)

    def emettre(self, texte: str) -> dict:
        """Construit la trame du message, mesure le signal, scelle l'émission.

        Rend un dict : octets utiles, bits, échantillons, durée, CRC, et le bloc Γ.
        """
        octets = texte.encode("utf-8")
        bits = trame.construire(octets)
        ech = afsk.moduler(bits)
        fcs = trame.crc16_x25(octets)
        donnees = {
            "texte": texte,
            "octets": len(octets),
            "bits": len(bits),
            "echantillons": len(ech),
            "duree_ms": round(1000 * len(ech) / afsk.FS, 3),
            "crc_x25": f"0x{fcs:04x}",
        }
        bloc = self.chaine.inscrire("emission", "EMIS", "message_scelle", donnees)
        return {"signal": ech, "bits": bits, "crc": fcs, "bloc": bloc, "donnees": donnees}


def verifier(chemin_journal, chemin_temoin, verificateur):
    """Vérifie la chaîne et l'accord du témoin. Rend le RapportTemoin du socle."""
    return verifier_temoin(chemin_journal, chemin_temoin, verificateur)


def scelleur_hmac(secret: bytes) -> ScelleurHMAC:
    return ScelleurHMAC(secret)
