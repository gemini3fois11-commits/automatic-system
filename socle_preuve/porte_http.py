"""Base HTTP commune des portes locales : boucle locale seulement, défenses web.

- Écoute exclusivement sur 127.0.0.1 : tout autre hôte est refusé à la construction.
- En-tête Host contrôlé (anti DNS-rebinding) ; Origin contrôlé sur les requêtes
  qui modifient l'état (anti-CSRF), en plus du cookie SameSite=Strict.
- En-têtes de sécurité sur chaque réponse ; corps JSON plafonné.
"""

import http.server
import json
import socket
import socketserver
import time
from http.cookies import SimpleCookie

HOTE = "127.0.0.1"
CORPS_MAX = 64 * 1024
ENTETES_SECURITE = {
    "Content-Security-Policy": "default-src 'self'; frame-ancestors 'none'; base-uri 'none'",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "no-store",
}


class Serveur(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True
    # La valeur par défaut (5) déborde dès une rafale de quelques dizaines de connexions locales :
    # le noyau laisse alors tomber des poignées de main et le client voit une réinitialisation
    # une seconde plus tard (mesuré : 2 à 5 échecs sur 40, tous à 1,02 s).
    request_queue_size = 128

    def __init__(self, port: int, gestionnaire, hote: str = HOTE):
        if hote != HOTE:
            raise ValueError("les portes du projet n'écoutent que sur 127.0.0.1")
        super().__init__((hote, port), gestionnaire)


DRAIN_MAX_OCTETS = 4 * 1024 * 1024
DRAIN_MAX_S = 2.0


def fermeture_differee(connexion, octets_max: int = DRAIN_MAX_OCTETS, delai_s: float = DRAIN_MAX_S) -> None:
    """Après une réponse d'erreur envoyée sans avoir lu le corps : fermer le sens écriture,
    puis vider ce qui arrive avant de fermer. Sans cela, le noyau répond par un RST pendant que
    le client écrit encore, et la réponse est perdue (constaté sous charge parallèle).

    Bornes assumées : au plus `octets_max` octets et `delai_s` secondes. Au-delà, la connexion
    est coupée et le client peut voir une réinitialisation : un corps démesuré ne mérite pas
    qu'on immobilise un fil d'exécution pour lui.
    """
    try:
        connexion.shutdown(socket.SHUT_WR)
    except OSError:
        return
    fin, lus = time.monotonic() + delai_s, 0
    while lus < octets_max:
        reste = fin - time.monotonic()
        if reste <= 0:
            break
        try:
            connexion.settimeout(reste)       # une seule attente peut consommer tout le budget restant
            bloc = connexion.recv(65536)
        except OSError:                       # délai écoulé ou connexion déjà rompue
            break
        if not bloc:                          # le client a fini et fermé : fermeture propre
            break
        lus += len(bloc)


class Gestionnaire(http.server.BaseHTTPRequestHandler):
    server_version = "omega-porte"
    sys_version = ""
    NOM_COOKIE = "omega_session"

    def log_message(self, fmt, *args):  # pas de journal brut sur stderr : l'audit est dans Γ
        pass

    def hotes_autorises(self) -> set[str]:
        port = self.server.server_address[1]
        return {f"127.0.0.1:{port}", f"localhost:{port}"}

    def origines_autorisees(self) -> set[str]:
        return {f"http://{h}" for h in self.hotes_autorises()}

    def controle_hote(self) -> bool:
        if self.headers.get("Host", "") not in self.hotes_autorises():
            self.repondre_json(421, {"erreur": "hote_refuse"})
            return False
        return True

    def controle_origine(self) -> bool:
        origine = self.headers.get("Origin")
        if origine is not None and origine not in self.origines_autorisees():
            self.repondre_json(403, {"erreur": "origine_refusee"})
            return False
        return True

    def handle_one_request(self):
        self._corps_lu = False
        super().handle_one_request()

    def corps_en_attente(self) -> bool:
        """Vrai si la requête déclare un corps que le gestionnaire n'a pas lu."""
        if getattr(self, "_corps_lu", False):
            return False
        return (self.headers.get("Content-Length", "0").strip() not in ("", "0")
                or "chunked" in self.headers.get("Transfer-Encoding", "").lower())

    def lire_corps(self, n: int) -> bytes:
        corps = self.rfile.read(n) if n else b""
        self._corps_lu = True
        return corps

    def envoyer(self, code: int, corps: bytes, type_: str, entetes: dict | None = None):
        en_attente = self.corps_en_attente()
        self.send_response(code)
        self.send_header("Content-Type", type_)
        self.send_header("Content-Length", str(len(corps)))
        if en_attente:
            self.send_header("Connection", "close")
        for k, v in {**ENTETES_SECURITE, **(entetes or {})}.items():
            if not (en_attente and k.lower() == "connection"):
                self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(corps)
        if en_attente:
            # Réponse partie sans avoir lu le corps : fermeture différée, sinon le client
            # qui écrit encore reçoit un RST à la place de la réponse.
            self.close_connection = True
            self.wfile.flush()
            fermeture_differee(self.connection)

    def repondre_json(self, code: int, objet, entetes: dict | None = None):
        self.envoyer(code, json.dumps(objet, ensure_ascii=False).encode(),
                     "application/json; charset=utf-8", entetes)

    def lire_json(self):
        """Retourne l'objet JSON du corps, ou None après avoir répondu l'erreur."""
        if "chunked" in self.headers.get("Transfer-Encoding", "").lower():
            self.repondre_json(411, {"erreur": "encodage_non_supporte"})
            return None
        try:
            n = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            n = -1
        if n < 0 or n > CORPS_MAX:
            self.repondre_json(413, {"erreur": "corps_trop_gros"})
            return None
        try:
            return json.loads(self.lire_corps(n) or b"{}")
        except (ValueError, UnicodeDecodeError):
            self.repondre_json(400, {"erreur": "json_invalide"})
            return None

    def jeton(self) -> str | None:
        cookie = SimpleCookie(self.headers.get("Cookie", ""))
        return cookie[self.NOM_COOKIE].value if self.NOM_COOKIE in cookie else None

    def cookie_session(self, jeton: str, duree_s: int) -> dict:
        return {"Set-Cookie": f"{self.NOM_COOKIE}={jeton}; HttpOnly; SameSite=Strict; Path=/; "
                              f"Max-Age={duree_s}"}

    def cookie_efface(self) -> dict:
        return {"Set-Cookie": f"{self.NOM_COOKIE}=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0"}
