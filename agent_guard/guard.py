"""GARDIEN — mandataire HTTP à allowlist exacte pour agents IA (blueprint §5.1).

Refuser avant de croire : une requête n'est transmise que si son hôte figure
exactement dans allowlist.json. Toute décision, autorisation ou refus, entre
dans une chaîne Γ du socle de preuve (guard_audit.jsonl, mode 600), avec un
témoin HMAC optionnel. Les heuristiques de canaux cachés marquent une requête,
elles ne décident jamais : le blocage vient de l'allowlist.

  python3 -m agent_guard.guard                 # 127.0.0.1:8090
  python3 -m agent_guard.guard --verify        # exit 0 intègre, 3 rompue
  curl --proxy http://127.0.0.1:8090 http://example.com/
  curl http://127.0.0.1:8090/api/status

Ce que le GARDIEN ne fait pas : il ne tunnelise pas TLS (CONNECT refusé), il
n'inspecte pas les réponses, il ne couvre que le trafic qui passe par lui.
"""

import argparse
import base64
import collections
import hashlib
import http.client
import json
import math
import os
import re
import sys
import urllib.parse

from socle_preuve.gamma import Chaine, lire_blocs, verifier_chaine
from socle_preuve.porte_http import Gestionnaire, Serveur
from socle_preuve.temoin import ScelleurHMAC, Temoin

DOSSIER = os.path.dirname(os.path.abspath(__file__))
PORT = 8090
CORPS_MAX = 1024 * 1024
REPONSE_MAX = 8 * 1024 * 1024
DELAI_AMONT_S = 10
SAUT_PAR_SAUT = {"connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "te",
                 "trailer", "transfer-encoding", "upgrade", "proxy-connection"}
B64 = re.compile(rb"[A-Za-z0-9+/_-]{40,}={0,2}")


class AllowlistInvalide(ValueError):
    pass


def charger_allowlist(chemin) -> frozenset[str]:
    with open(chemin, encoding="utf-8") as fh:
        hotes = json.load(fh)["hotes"]
    for h in hotes:
        if not isinstance(h, str) or not re.fullmatch(r"[a-z0-9]([a-z0-9.-]*[a-z0-9])?", h):
            raise AllowlistInvalide(f"entrée non exacte refusée : {h!r} (aucun joker, minuscules)")
    return frozenset(hotes)


def entropie(octets: bytes) -> float:
    if not octets:
        return 0.0
    n = len(octets)
    return -sum(c / n * math.log2(c / n) for c in collections.Counter(octets).values())


def signaux(url: str, hote: str, chemin: str, corps: bytes) -> list[str]:
    """Heuristiques de canal caché. Signal, jamais preuve."""
    trouves = []
    requete = urllib.parse.urlsplit(chemin).query.encode()
    if len(corps) >= 64 and entropie(corps) > 5.0 or len(requete) >= 64 and entropie(requete) > 4.5:
        trouves.append("haute_entropie")
    if B64.search(corps) or B64.search(requete):
        trouves.append("base64_suspect")
    segments = [s for s in urllib.parse.unquote(urllib.parse.urlsplit(chemin).path).split("/") if s]
    if any(len(s) >= 48 or (len(s) >= 32 and re.fullmatch(r"[A-Za-z0-9+/=_-]+", s)) for s in segments):
        trouves.append("exfiltration_chemin")
    etiquettes = hote.split(".")
    if any(len(e) >= 32 for e in etiquettes) or len(hote) > 100 or len(etiquettes) > 6:
        trouves.append("exfiltration_hote")
    if (len(url) > 2048 or "@" in urllib.parse.urlsplit(url).netloc or "%25" in url
            or re.search(r"%(0[0-9a-fA-F]|1[0-9a-fA-F]|7[fF])", url) or re.search(r"\s", url)):
        trouves.append("url_anormale")
    return trouves


def connecter_direct(hote: str, port: int) -> http.client.HTTPConnection:
    """Connexion vers l'origine, ou vers le proxy amont GARDIEN_AMONT relu à chaque requête."""
    amont = os.environ.get("GARDIEN_AMONT")
    if not amont:
        return http.client.HTTPConnection(hote, port, timeout=DELAI_AMONT_S)
    u = urllib.parse.urlsplit(amont)
    conn = http.client.HTTPConnection(u.hostname, u.port or 80, timeout=DELAI_AMONT_S)
    conn._omega_amont = u   # identifiants lus ici, jamais journalisés
    return conn


class Gardien:
    def __init__(self, allowlist: frozenset[str], journal: Chaine, connecter=connecter_direct):
        self.allowlist = allowlist
        self.journal = journal
        self.connecter = connecter

    def inscrire(self, decision: str, raison: str, methode: str, hote: str, chemin: str,
                 corps: bytes, sig: list[str], statut: int, taille: int = 0):
        # Ni le chemin ni le corps en clair : leurs empreintes. Le journal ne doit pas
        # devenir lui-même le canal d'exfiltration qu'il documente.
        self.journal.inscrire("requete", decision, raison, {
            "methode": methode, "hote": hote[:253],
            "chemin_sha256": hashlib.sha256(chemin.encode()).hexdigest(),
            "corps_sha256": hashlib.sha256(corps).hexdigest(), "corps_octets": len(corps),
            "signaux": sig, "statut": statut, "reponse_octets": taille})

    def statut(self) -> dict:
        blocs, rapport = lire_blocs(self.journal.chemin)
        decisions = collections.Counter(b["decision"] for b in blocs)
        refus = collections.Counter(b["raison"] for b in blocs if b["decision"] == "REFUS")
        sig = collections.Counter(s for b in blocs for s in b.get("donnees", {}).get("signaux", []))
        return {"decisions": dict(decisions), "refus_par_raison": dict(refus),
                "signaux_par_code": dict(sig), "allowlist": sorted(self.allowlist),
                "chaine": {"integre": rapport.integre, "blocs": rapport.blocs,
                           "seq_fautif": rapport.seq_fautif, "raison": rapport.raison}}


class Gestion(Gestionnaire):
    server_version = "omega-gardien"

    @property
    def g(self) -> Gardien:
        return self.server.gardien

    def refuser(self, code, raison, methode, hote, chemin, corps=b"", sig=()):
        self.g.inscrire("REFUS", raison, methode, hote, chemin, corps, list(sig), code)
        self.repondre_json(code, {"refus": raison}, {"Connection": "close"})

    def do_CONNECT(self):
        hote = self.path.rsplit(":", 1)[0].lower()
        self.refuser(403, "tls_non_inspecte", "CONNECT", hote, "")

    def traiter(self):
        self.close_connection = True
        if not re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", self.path):
            if self.command == "GET" and self.path == "/api/status":
                if self.controle_hote():
                    self.repondre_json(200, self.g.statut())
                return
            self.repondre_json(400, {"erreur": "requete_non_mandataire"})
            return
        url = self.path
        u = urllib.parse.urlsplit(url)
        hote = (u.hostname or "").lower()
        chemin = urllib.parse.urlunsplit(("", "", u.path or "/", u.query, ""))
        if u.scheme.lower() != "http":
            self.refuser(403, "schema_non_http", self.command, hote, chemin)
            return
        if "chunked" in self.headers.get("Transfer-Encoding", "").lower():
            self.refuser(411, "encodage_non_supporte", self.command, hote, chemin)
            return
        try:
            n = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            n = -1
        if n < 0 or n > CORPS_MAX:
            self.refuser(413, "corps_trop_gros", self.command, hote, chemin)
            return
        corps = self.rfile.read(n) if n else b""
        sig = signaux(url, hote, chemin, corps)
        try:
            port = u.port or 80
        except ValueError:
            port = -1
        if hote not in self.g.allowlist:
            self.refuser(403, "hote_non_autorise", self.command, hote, chemin, corps, sig)
            return
        if port != 80:
            self.refuser(403, "port_non_autorise", self.command, hote, chemin, corps, sig)
            return
        entetes = {k: v for k, v in self.headers.items() if k.lower() not in SAUT_PAR_SAUT}
        entetes["Host"] = hote
        entetes["Connection"] = "close"
        try:
            conn = self.g.connecter(hote, port)
            amont = getattr(conn, "_omega_amont", None)
            cible = url if amont else chemin
            if amont is not None and amont.username:
                jeton = f"{urllib.parse.unquote(amont.username)}:{urllib.parse.unquote(amont.password or '')}"
                entetes["Proxy-Authorization"] = "Basic " + base64.b64encode(jeton.encode()).decode()
            conn.request(self.command, cible, body=corps or None, headers=entetes)
            rep = conn.getresponse()
            donnees = rep.read(REPONSE_MAX + 1)
            conn.close()
        except (OSError, http.client.HTTPException):
            self.refuser(502, "amont_injoignable", self.command, hote, chemin, corps, sig)
            return
        if len(donnees) > REPONSE_MAX:
            self.refuser(502, "reponse_trop_grosse", self.command, hote, chemin, corps, sig)
            return
        self.g.inscrire("AUTORISE", "allowlist", self.command, hote, chemin, corps, sig,
                        rep.status, len(donnees))
        self.send_response(rep.status)
        for k, v in rep.getheaders():
            if k.lower() not in SAUT_PAR_SAUT and k.lower() != "content-length":
                self.send_header(k, v)
        self.send_header("Content-Length", str(len(donnees)))
        self.send_header("Connection", "close")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(donnees)

    do_GET = do_POST = do_PUT = do_DELETE = do_HEAD = do_PATCH = do_OPTIONS = traiter


def construire(port=PORT, *, allowlist=None, journal=None, temoin_secret=None,
               connecter=connecter_direct) -> Serveur:
    hotes = charger_allowlist(allowlist or os.path.join(DOSSIER, "allowlist.json"))
    chemin = journal or os.path.join(DOSSIER, "guard_audit.jsonl")
    temoin = None
    if temoin_secret:
        with open(temoin_secret, "rb") as fh:
            temoin = Temoin(chemin + ".temoin", ScelleurHMAC(fh.read()))
    serveur = Serveur(port, Gestion)
    serveur.gardien = Gardien(hotes, Chaine(chemin, temoin=temoin), connecter)
    return serveur


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python3 -m agent_guard.guard")
    ap.add_argument("--port", type=int, default=PORT)
    ap.add_argument("--allowlist")
    ap.add_argument("--journal", default=os.path.join(DOSSIER, "guard_audit.jsonl"))
    ap.add_argument("--temoin-secret", help="secret HMAC du témoin (mode 600)")
    ap.add_argument("--verify", action="store_true", help="vérifie la chaîne et sort")
    a = ap.parse_args(argv)
    if a.verify:
        if not os.path.exists(a.journal):
            print(f"journal absent : {a.journal}")
            return 2
        r = verifier_chaine(a.journal)
        print(r)
        return 0 if r.integre else 3
    serveur = construire(a.port, allowlist=a.allowlist, journal=a.journal,
                         temoin_secret=a.temoin_secret)
    print(f"GARDIEN sur http://127.0.0.1:{a.port} — allowlist : "
          f"{', '.join(sorted(serveur.gardien.allowlist))}")
    try:
        serveur.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        serveur.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
