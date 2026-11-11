"""Serveur de journal TLS durci (blueprint §6.2) : la saturation est un refus propre.

TLS 1.3 uniquement, 127.0.0.1 uniquement, certificat épinglé par le client, corps
plafonné, délai de lecture (anti slowloris), nombre de connexions simultanées borné :
au-delà, réponse immédiate 503 `refus_saturation` au lieu d'une file qui gonfle.
Chaque entrée reçue est inscrite dans une chaîne Γ.
"""

import contextlib
import http.client
import http.server
import json
import os
import socket
import socketserver
import ssl
import subprocess
import tempfile
import threading
import time

from plateforme_omega.commun import conclure, sortir
from socle_preuve.gamma import Chaine, verifier_chaine

CORPS_MAX = 16 * 1024
CONNEXIONS_MAX = 4
DELAI_LECTURE_S = 2.0


def certificat(dossier) -> tuple[str, str]:
    cle, cert = os.path.join(dossier, "cle.pem"), os.path.join(dossier, "cert.pem")
    subprocess.run(["openssl", "req", "-x509", "-newkey", "ec", "-pkeyopt", "ec_paramgen_curve:P-256",
                    "-nodes", "-keyout", cle, "-out", cert, "-days", "1", "-subj", "/CN=127.0.0.1",
                    "-addext", "subjectAltName=IP:127.0.0.1"], check=True, capture_output=True)
    os.chmod(cle, 0o600)
    return cle, cert


class Gestion(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def setup(self):
        # Poignée de main dans le thread de la connexion, jamais dans la boucle d'acceptation :
        # un client muet n'immobilise que lui-même.
        self.request.settimeout(DELAI_LECTURE_S)
        self.request.do_handshake()
        super().setup()

    def handle(self):
        if not self.server.places.acquire(blocking=False):
            self.wfile.write(b"HTTP/1.1 503 Service Unavailable\r\nContent-Type: application/json\r\n"
                             b"Content-Length: 30\r\nConnection: close\r\n\r\n{\"refus\": \"refus_saturation\"}\n")
            return
        try:
            super().handle()
        except (TimeoutError, socket.timeout, ssl.SSLError, ConnectionError):
            pass
        finally:
            self.server.places.release()

    def repondre(self, code, objet):
        corps = json.dumps(objet).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(corps)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(corps)

    def do_POST(self):
        self.close_connection = True
        if self.path != "/journal":
            return self.repondre(404, {"erreur": "introuvable"})
        try:
            n = int(self.headers.get("Content-Length", "-1"))
        except ValueError:
            n = -1
        if n < 0 or n > CORPS_MAX:
            return self.repondre(413, {"refus": "corps_trop_gros"})
        try:
            entree = json.loads(self.rfile.read(n))
            if not isinstance(entree, dict):
                raise ValueError
        except (ValueError, UnicodeDecodeError):
            return self.repondre(400, {"refus": "json_invalide"})
        bloc = self.server.journal.inscrire("entree", "RECU", "journal_tls", entree)
        self.repondre(201, {"seq": bloc["seq"], "hash": bloc["hash"]})

    def do_GET(self):
        self.close_connection = True
        if self.path == "/journal/etat":
            r = verifier_chaine(self.server.journal.chemin)
            return self.repondre(200, {"integre": r.integre, "blocs": r.blocs})
        self.repondre(404, {"erreur": "introuvable"})


class ServeurTLS(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True

    def __init__(self, cle, cert, journal):
        super().__init__(("127.0.0.1", 0), Gestion)
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.minimum_version = ssl.TLSVersion.TLSv1_3
        ctx.load_cert_chain(cert, cle)
        self.ctx = ctx
        self.places = threading.BoundedSemaphore(CONNEXIONS_MAX)
        self.journal = journal

    def get_request(self):
        sock, adr = self.socket.accept()
        return self.ctx.wrap_socket(sock, server_side=True, do_handshake_on_connect=False), adr

    def handle_error(self, request, client_address):
        self.erreurs_poignee = getattr(self, "erreurs_poignee", 0) + 1   # compté, pas de trace sur stderr


def client(cert, version=ssl.TLSVersion.TLSv1_3, verifier=True):
    ctx = ssl.create_default_context(cafile=cert if verifier else None)
    ctx.minimum_version = ctx.maximum_version = version
    return ctx


def requete(port, ctx, methode, chemin, corps=None):
    conn = http.client.HTTPSConnection("127.0.0.1", port, context=ctx, timeout=5)
    conn.request(methode, chemin, body=corps, headers={"Content-Type": "application/json"})
    r = conn.getresponse()
    d = r.read()
    conn.close()
    return r.status, json.loads(d)


def mesurer() -> dict:
    res = {}
    with tempfile.TemporaryDirectory() as d:
        cle, cert = certificat(d)
        s = ServeurTLS(cle, cert, Chaine(os.path.join(d, "journal.jsonl")))
        threading.Thread(target=s.serve_forever, daemon=True).start()
        port = s.server_address[1]
        try:
            res["tls13_ok"] = requete(port, client(cert), "POST", "/journal", b'{"evenement": "test"}')[0] == 201
            for nom, appel in (
                    ("tls12_refuse", lambda: requete(port, client(cert, ssl.TLSVersion.TLSv1_2), "GET", "/journal/etat")),
                    ("certificat_non_epingle_refuse", lambda: requete(port, client(None), "GET", "/journal/etat"))):
                try:
                    appel()
                    res[nom] = False
                except (ssl.SSLError, ConnectionError, OSError):
                    res[nom] = True
            with socket.create_connection(("127.0.0.1", port), timeout=5) as brut:
                brut.sendall(b"GET /journal/etat HTTP/1.1\r\nHost: x\r\n\r\n")
                try:
                    res["http_en_clair_refuse"] = not brut.recv(100).startswith(b"HTTP/1.1 200")
                except (ConnectionError, socket.timeout):
                    res["http_en_clair_refuse"] = True
            muettes = [socket.create_connection(("127.0.0.1", port), timeout=5) for _ in range(3)]
            t0 = time.perf_counter()
            ok = requete(port, client(cert), "GET", "/journal/etat")[0] == 200
            res["poignee_muette"] = {"ok": ok, "ms": (time.perf_counter() - t0) * 1000}
            for m in muettes:
                m.close()
            res["corps_trop_gros"] = requete(port, client(cert), "POST", "/journal", b"x" * (CORPS_MAX + 1))[0] == 413
            res["json_invalide"] = requete(port, client(cert), "POST", "/journal", b"[1, 2")[0] == 400
            # Saturation : 4 connexions TLS ouvertes qui ne disent rien occupent toutes les places.
            lentes = []
            for _ in range(CONNEXIONS_MAX):
                c = client(cert).wrap_socket(socket.create_connection(("127.0.0.1", port), timeout=5),
                                             server_hostname="127.0.0.1")
                c.sendall(b"POST /journal HTTP/1.1\r\n")
                lentes.append(c)
            time.sleep(0.3)
            t0 = time.perf_counter()
            code, corps = requete(port, client(cert), "GET", "/journal/etat")
            res["saturation"] = {"code": code, "corps": corps, "ms": (time.perf_counter() - t0) * 1000}
            for c in lentes:
                with contextlib.suppress(OSError):
                    c.close()
            time.sleep(DELAI_LECTURE_S + 0.5)
            code, etat = requete(port, client(cert), "GET", "/journal/etat")
            res["reprise_apres_saturation"] = code == 200
            res["journal"] = etat
            res["ecoute"] = s.server_address[0]
        finally:
            s.shutdown()
            s.server_close()
    return res


def main() -> int:
    m = mesurer()
    sat = m["saturation"]
    return conclure("tls", [
        ("TLS 1.3 avec certificat épinglé : entrée inscrite (201)", m["tls13_ok"], ""),
        ("client TLS 1.2 refusé", m["tls12_refuse"], ""),
        ("client sans le certificat épinglé : échec de vérification", m["certificat_non_epingle_refuse"], ""),
        ("HTTP en clair sur le port TLS : refusé", m["http_en_clair_refuse"], ""),
        ("3 clients TCP muets (sans ClientHello) n'immobilisent pas le serveur",
         m["poignee_muette"]["ok"] and m["poignee_muette"]["ms"] < 1000, f"{m['poignee_muette']['ms']:.0f} ms"),
        ("corps > 16 Kio : 413", m["corps_trop_gros"], ""),
        ("JSON invalide : 400", m["json_invalide"], ""),
        ("saturation : 503 refus_saturation immédiat", sat["code"] == 503 and sat["corps"] == {"refus": "refus_saturation"}
         and sat["ms"] < 1000, f"{sat['ms']:.0f} ms"),
        ("le service reprend une fois les connexions lentes coupées", m["reprise_apres_saturation"], ""),
        ("journal Γ intègre", m["journal"]["integre"], str(m["journal"])),
        ("écoute sur 127.0.0.1 seulement", m["ecoute"] == "127.0.0.1", ""),
    ], m, ["Certificat auto-signé jetable généré par openssl à chaque exécution ; pas d'autorité réelle.",
           "Pas d'authentification du client : le serveur journalise ce qu'on lui envoie, il ne l'atteste pas."])


if __name__ == "__main__":
    sortir(main())
