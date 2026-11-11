"""Base HTTP commune des portes locales : boucle locale seulement, défenses web.

- Écoute exclusivement sur 127.0.0.1 : tout autre hôte est refusé à la construction.
- En-tête Host contrôlé (anti DNS-rebinding) ; Origin contrôlé sur les requêtes
  qui modifient l'état (anti-CSRF), en plus du cookie SameSite=Strict.
- En-têtes de sécurité sur chaque réponse ; corps JSON plafonné.
"""

import http.server
import json
import socketserver
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

    def __init__(self, port: int, gestionnaire, hote: str = HOTE):
        if hote != HOTE:
            raise ValueError("les portes du projet n'écoutent que sur 127.0.0.1")
        super().__init__((hote, port), gestionnaire)


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

    def envoyer(self, code: int, corps: bytes, type_: str, entetes: dict | None = None):
        self.send_response(code)
        self.send_header("Content-Type", type_)
        self.send_header("Content-Length", str(len(corps)))
        for k, v in {**ENTETES_SECURITE, **(entetes or {})}.items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(corps)

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
            return json.loads(self.rfile.read(n) or b"{}")
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
