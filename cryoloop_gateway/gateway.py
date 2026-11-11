"""Passerelle CryoLoop — le patron des portes (blueprint §3.4).

Reçoit, vérifie, inscrit, répond un verdict. **N'exécute rien** : c'est un choix
d'architecture. Écoute 127.0.0.1:8077, session authentifiée, tickets Ed25519
vérifiés contre une clé publique épinglée, anti-rejeu persistant, journal Γ.

Tant que le propriétaire n'a pas lancé keygen.py puis choisi son mot de passe,
la passerelle est non initialisée : elle refuse tout ticket.

  python3 -m cryoloop_gateway.gateway [--etat DOSSIER] [--temoin-secret FICHIER]
"""

import argparse
import json
import os
import sys
import threading
import time

from socle_preuve import ed25519
from socle_preuve.auth import SESSION_S, Authentificateur, ErreurAuth
from socle_preuve.gamma import Chaine, lire_blocs
from socle_preuve.porte_http import Gestionnaire, Serveur
from socle_preuve.temoin import ScelleurHMAC, Temoin

DOSSIER = os.path.dirname(os.path.abspath(__file__))
PORT = 8077
FENETRE_MAX_S = 3600
DECALAGE_TOLERE_S = 60
CHAMPS = {"id": str, "emis": int, "expire": int, "action": str, "parametres": dict}
CODES_AUTH = {"setup_mode": 403, "verrouille": 403, "identifiants_invalides": 401,
              "mot_de_passe_trop_court": 400, "deja_configure": 409}


def octets_ticket(ticket: dict) -> bytes:
    """Forme canonique signée : JSON trié, sans espaces, UTF-8."""
    return json.dumps(ticket, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def signer_ticket(graine: bytes, ticket: dict) -> dict:
    return {"ticket": ticket, "signature": ed25519.signer(graine, octets_ticket(ticket)).hex()}


class Passerelle:
    def __init__(self, etat: str, *, horloge=time.time, delai_echec=0.5, temoin_secret=None):
        self.etat = etat
        os.makedirs(etat, mode=0o700, exist_ok=True)
        self.horloge = horloge
        chemin = os.path.join(etat, "passerelle.jsonl")
        temoin = None
        if temoin_secret:
            with open(temoin_secret, "rb") as fh:
                temoin = Temoin(chemin + ".temoin", ScelleurHMAC(fh.read()))
        self.journal = Chaine(chemin, temoin=temoin)     # refuse de démarrer sur une chaîne rompue
        self.auth = Authentificateur(os.path.join(etat, "auth.json"), delai_echec=delai_echec,
                                     evenement=lambda t, d: self.journal.inscrire("auth", t, t, d))
        self._verrou = threading.Lock()
        blocs, _ = lire_blocs(chemin)
        self.vus = {b["donnees"]["id"] for b in blocs
                    if b["type"] == "ticket" and b["decision"] == "ACCEPTE"}

    @property
    def cle_publique(self) -> bytes | None:
        try:
            with open(os.path.join(self.etat, "cle_publique.hex")) as fh:
                cle = bytes.fromhex(fh.read().strip())
            return cle if len(cle) == 32 else None
        except (FileNotFoundError, ValueError):
            return None

    def verdict(self, corps) -> tuple[int, dict]:
        cle = self.cle_publique
        if cle is None:
            return 503, {"refus": "non_initialisee"}
        ticket = corps.get("ticket") if isinstance(corps, dict) else None
        signature = corps.get("signature") if isinstance(corps, dict) else None
        if (not isinstance(ticket, dict) or set(ticket) != set(CHAMPS)
                or any(type(ticket[k]) is not t for k, t in CHAMPS.items())
                or not isinstance(signature, str) or len(ticket["id"]) != 32):
            return self._refus(400, "ticket_malforme", ticket)
        try:
            sig = bytes.fromhex(signature)
        except ValueError:
            sig = b""
        if not ed25519.verifier(cle, octets_ticket(ticket), sig):
            return self._refus(403, "signature_invalide", ticket)
        maintenant = int(self.horloge())
        if ticket["expire"] - ticket["emis"] > FENETRE_MAX_S or ticket["expire"] <= ticket["emis"]:
            return self._refus(403, "fenetre_invalide", ticket)
        if ticket["emis"] > maintenant + DECALAGE_TOLERE_S:
            return self._refus(403, "ticket_pas_encore_valide", ticket)
        if maintenant >= ticket["expire"]:
            return self._refus(403, "ticket_expire", ticket)
        with self._verrou:
            if ticket["id"] in self.vus:
                return self._refus(403, "ticket_rejoue", ticket)
            self.vus.add(ticket["id"])
            bloc = self.journal.inscrire("ticket", "ACCEPTE", "signature_valide", self._resume(ticket))
        # Accepter un ticket, c'est l'inscrire. Rien n'est exécuté, jamais.
        return 200, {"verdict": "ACCEPTE", "seq": bloc["seq"], "execute": False}

    @staticmethod
    def _resume(ticket) -> dict:
        if not isinstance(ticket, dict):
            return {}
        return {"id": str(ticket.get("id"))[:64], "action": str(ticket.get("action"))[:128],
                "emis": ticket.get("emis"), "expire": ticket.get("expire")}

    def _refus(self, code, raison, ticket):
        self.journal.inscrire("ticket", "REFUS", raison, self._resume(ticket))
        return code, {"refus": raison}


class Gestion(Gestionnaire):
    server_version = "omega-passerelle"

    @property
    def p(self) -> Passerelle:
        return self.server.passerelle

    def do_GET(self):
        if not self.controle_hote():
            return
        if self.path == "/api/etat":
            self.repondre_json(200, {"setup_mode": self.p.auth.setup_mode,
                                     "cle_epinglee": self.p.cle_publique is not None,
                                     "execute": False})
        elif self.path == "/api/journal":
            if not self.p.auth.valider(self.jeton()):
                self.repondre_json(401, {"erreur": "non_authentifie"})
                return
            blocs, rapport = lire_blocs(self.p.journal.chemin)
            self.repondre_json(200, {"integre": rapport.integre, "blocs": rapport.blocs,
                                     "derniers": blocs[-20:]})
        else:
            self.repondre_json(404, {"erreur": "introuvable"})

    def do_POST(self):
        if not (self.controle_hote() and self.controle_origine()):
            return
        corps = self.lire_json()
        if corps is None:
            return
        if not isinstance(corps, dict):
            self.repondre_json(400, {"erreur": "json_invalide"})
            return
        try:
            if self.path == "/api/setup":
                if not self.p.auth.setup_mode:
                    raise ErreurAuth("deja_configure")
                self.p.auth.configurer(corps.get("mot_de_passe"))
                self.repondre_json(200, {"setup": "ok"})
            elif self.path == "/api/login":
                jeton = self.p.auth.connecter(corps.get("mot_de_passe"))
                self.repondre_json(200, {"session": "ouverte"}, self.cookie_session(jeton, SESSION_S))
            elif self.path == "/api/logout":
                self.p.auth.deconnecter(self.jeton())
                self.repondre_json(200, {"session": "fermee"}, self.cookie_efface())
            elif self.path == "/api/ticket":
                if not self.p.auth.valider(self.jeton()):
                    self.repondre_json(401, {"erreur": "non_authentifie"})
                    return
                self.repondre_json(*self.p.verdict(corps))
            else:
                self.repondre_json(404, {"erreur": "introuvable"})
        except ErreurAuth as e:
            self.repondre_json(CODES_AUTH.get(e.code, 400), {"erreur": e.code})


def construire(port=PORT, etat=None, **options) -> Serveur:
    passerelle = Passerelle(etat or os.path.join(DOSSIER, "etat"), **options)  # avant le socket
    serveur = Serveur(port, Gestion)
    serveur.passerelle = passerelle
    return serveur


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python3 -m cryoloop_gateway.gateway")
    ap.add_argument("--port", type=int, default=PORT)
    ap.add_argument("--etat", default=os.path.join(DOSSIER, "etat"))
    ap.add_argument("--temoin-secret")
    a = ap.parse_args(argv)
    s = construire(a.port, a.etat, temoin_secret=a.temoin_secret)
    p = s.passerelle
    print(f"Passerelle CryoLoop sur http://127.0.0.1:{a.port} — "
          f"{'SETUP_MODE' if p.auth.setup_mode else 'configurée'}, "
          f"clé {'épinglée' if p.cle_publique else 'NON épinglée (lancer keygen.py)'}")
    try:
        s.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        s.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
