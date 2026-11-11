"""Banc du GARDIEN : de vraies requêtes HTTP, à travers un vrai GARDIEN, vers une origine locale.

Le proxy sortant de cet environnement ne relaie que le HTTPS (CONNECT). Le trafic
HTTP en clair vers les trois hôtes publics de l'allowlist ne peut donc pas être joué
ici : la connexion amont est dirigée vers une origine locale qui se fait passer pour eux.
La décision, la journalisation et le relais sont exactement le code de production.

  python3 -m agent_guard.banc        # écrit agent_guard/guard_evidence.json
"""

import base64
import contextlib
import http.client
import http.server
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading

from agent_guard.guard import DOSSIER, connecter_direct, construire
from outils.evidence import ecrire
from socle_preuve.temoin import ScelleurHMAC, verifier_temoin

RACINE = os.path.dirname(DOSSIER)


class Origine(http.server.BaseHTTPRequestHandler):
    recues = []

    def log_message(self, *a):
        pass

    def repondre(self):
        n = int(self.headers.get("Content-Length", "0"))
        corps = self.rfile.read(n) if n else b""
        Origine.recues.append({"chemin": self.path, "entetes": dict(self.headers), "corps": corps})
        reponse = f"origine:{self.headers.get('Host')}:{self.path}".encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(reponse)))
        self.send_header("Connection", "keep-alive")     # saut par saut : ne doit pas passer
        self.end_headers()
        self.wfile.write(reponse)

    do_GET = do_POST = repondre


def _port_libre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@contextlib.contextmanager
def _servir(serveur):
    t = threading.Thread(target=serveur.serve_forever, daemon=True)
    t.start()
    try:
        yield serveur
    finally:
        serveur.shutdown()
        serveur.server_close()


def _requete(port, methode, cible, corps=None, entetes=None):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    conn.request(methode, cible, body=corps, headers=entetes or {})
    rep = conn.getresponse()
    donnees = rep.read()
    conn.close()
    try:
        donnees_json = json.loads(donnees) if rep.getheader("Content-Type", "").startswith(
            "application/json") else None
    except ValueError:
        donnees_json = None
    return rep.status, donnees, donnees_json, dict(rep.getheaders())


def jouer() -> dict:
    Origine.recues = []
    resultats = []

    def cas(nom, ok, detail=""):
        resultats.append({"cas": nom, "ok": bool(ok), "detail": detail})

    with tempfile.TemporaryDirectory() as tmp, \
            _servir(http.server.ThreadingHTTPServer(("127.0.0.1", 0), Origine)) as origine:
        port_origine = origine.server_address[1]
        secret = os.path.join(tmp, "temoin.secret")
        with open(os.open(secret, os.O_WRONLY | os.O_CREAT, 0o600), "wb") as fh:
            fh.write(os.urandom(32))
        journal = os.path.join(tmp, "guard_audit.jsonl")
        port_mort = _port_libre()

        def connecter(hote, port):
            if hote == "neverssl.com":            # amont en panne
                return http.client.HTTPConnection("127.0.0.1", port_mort, timeout=2)
            return http.client.HTTPConnection("127.0.0.1", port_origine, timeout=5)

        gardien = construire(0, journal=journal, temoin_secret=secret, connecter=connecter)
        with _servir(gardien):
            p = gardien.server_address[1]
            avant = len(Origine.recues)
            code, corps, _, ent = _requete(p, "GET", "http://example.com/index.html",
                                           entetes={"Host": "example.com", "Proxy-Authorization": "Basic eDp5"})
            relayee = Origine.recues[-1] if len(Origine.recues) > avant else {}
            cas("example.com autorisé : 200 relayé", code == 200 and corps == b"origine:example.com:/index.html",
                f"{code} {corps[:40]!r}")
            cas("Proxy-Authorization du client non transmis à l'origine",
                "Proxy-Authorization" not in relayee.get("entetes", {}))
            cas("en-tête saut par saut Connection: keep-alive non relayé",
                ent.get("Connection") == "close")
            code, corps, _, _ = _requete(p, "GET", "http://info.cern.ch/hypertext/WWW/TheProject.html")
            cas("info.cern.ch autorisé : 200 relayé", code == 200, str(code))
            n = len(Origine.recues)
            code, _, j, _ = _requete(p, "GET", "http://example.org/")
            cas("example.org : 403 hote_non_autorise, rien transmis",
                code == 403 and j == {"refus": "hote_non_autorise"} and len(Origine.recues) == n,
                f"{code} {j}")
            code, _, j, _ = _requete(p, "CONNECT", "example.com:443")
            cas("CONNECT https : 403 tls_non_inspecte", code == 403 and j == {"refus": "tls_non_inspecte"},
                f"{code} {j}")
            code, _, j, _ = _requete(p, "GET", "https://example.com/")
            cas("https:// sans CONNECT : 403 schema_non_http", code == 403 and j["refus"] == "schema_non_http")
            code, _, j, _ = _requete(p, "GET", "ftp://example.com/x")
            cas("ftp:// : 403 schema_non_http", code == 403 and j["refus"] == "schema_non_http")
            code, _, j, _ = _requete(p, "GET", "http://example.com:8080/")
            cas("port 8080 : 403 port_non_autorise", code == 403 and j["refus"] == "port_non_autorise")
            code, _, j, _ = _requete(p, "POST", "http://example.com/", corps=b"x" * (1024 * 1024 + 1))
            cas("corps de 1 Mio + 1 : 413 corps_trop_gros", code == 413 and j["refus"] == "corps_trop_gros")
            code, _, j, _ = _requete(p, "POST", "http://example.com/", corps=iter([b"abc"]),
                                     entetes={"Transfer-Encoding": "chunked"})
            cas("chunked : 411 encodage_non_supporte", code == 411 and j["refus"] == "encodage_non_supporte")
            code, _, j, _ = _requete(p, "GET", "http://neverssl.com/")
            cas("amont en panne : 502 amont_injoignable", code == 502 and j["refus"] == "amont_injoignable")
            charge = base64.b64encode(os.urandom(300))
            code, _, _, _ = _requete(p, "POST", "http://example.com/upload", corps=charge)
            cas("POST base64 vers hôte autorisé : transmis (200), donc signalé seulement", code == 200)
            code, _, _, _ = _requete(p, "GET", "http://example.com/" + "QUJD" * 16)
            code2, _, _, _ = _requete(p, "GET", "http://" + "a1b2c3d4" * 5 + ".exfil.example.net/")
            code3, _, _, _ = _requete(p, "GET", "http://user:pw@example.com/")
            cas("exfiltration dans le chemin, dans l'hôte, URL avec identifiants", code == 200 and code2 == 403,
                f"{code} {code2} {code3}")
            code, _, j, _ = _requete(p, "GET", "/api/status", entetes={"Host": "attaquant.example:80"})
            cas("/api/status avec un Host étranger : 421 (anti DNS-rebinding)", code == 421)
            code, _, statut, _ = _requete(p, "GET", "/api/status", entetes={"Host": f"127.0.0.1:{p}"})
            sig = statut["signaux_par_code"]
            cas("/api/status : décisions, refus et signaux comptés depuis Γ",
                code == 200 and statut["chaine"]["integre"]
                and {"base64_suspect", "haute_entropie", "exfiltration_chemin", "exfiltration_hote",
                     "url_anormale"} <= set(sig),
                json.dumps(statut["refus_par_raison"]))

        # Proxy amont : identifiants relus à chaque requête, envoyés à l'amont, jamais journalisés.
        Origine.recues = []
        journal2 = os.path.join(tmp, "amont.jsonl")
        os.environ["GARDIEN_AMONT"] = f"http://agent:S3cret-amont@127.0.0.1:{port_origine}"
        try:
            g2 = construire(0, journal=journal2, connecter=connecter_direct)
            with _servir(g2):
                code, _, _, _ = _requete(g2.server_address[1], "GET", "http://example.com/via-amont")
        finally:
            del os.environ["GARDIEN_AMONT"]
        recu = Origine.recues[-1] if Origine.recues else {"entetes": {}, "chemin": ""}
        attendu = "Basic " + base64.b64encode(b"agent:S3cret-amont").decode()
        with open(journal2, encoding="utf-8") as fh:
            contenu_journal2 = fh.read()
        cas("proxy amont : forme absolue + Proxy-Authorization envoyés à l'amont",
            code == 200 and recu["chemin"] == "http://example.com/via-amont"
            and recu["entetes"].get("Proxy-Authorization") == attendu)
        cas("identifiants amont absents du journal", "S3cret-amont" not in contenu_journal2
            and base64.b64encode(b"agent:S3cret-amont").decode() not in contenu_journal2)

        with open(journal, encoding="utf-8") as fh:
            contenu = fh.read()
        cas("journal en mode 600, sans corps ni chemin en clair",
            oct(os.stat(journal).st_mode & 0o777) == "0o600" and "QUJD" not in contenu
            and charge.decode()[:40] not in contenu)
        verif = lambda: subprocess.run([sys.executable, "-m", "agent_guard.guard", "--verify",
                                        "--journal", journal], cwd=RACINE, capture_output=True, text=True)
        r_ok = verif()
        blocs = [json.loads(l) for l in contenu.splitlines()]
        blocs[1]["decision"] = "REFUS" if blocs[1]["decision"] == "AUTORISE" else "AUTORISE"
        with open(journal, "w", encoding="utf-8") as fh:
            fh.writelines(json.dumps(b) + "\n" for b in blocs)
        r_ko = verif()
        cas("--verify : exit 0 sur chaîne intègre, exit 3 et seq 1 après falsification",
            r_ok.returncode == 0 and r_ko.returncode == 3 and "seq 1" in r_ko.stdout,
            f"{r_ok.returncode} / {r_ko.returncode} {r_ko.stdout.strip()}")
        with open(secret, "rb") as fh:
            temoin = verifier_temoin(journal, journal + ".temoin", ScelleurHMAC(fh.read()))
        cas("le témoin refuse aussi le journal falsifié", not temoin.chaine.integre or not temoin.accord)
    return {"cas": resultats, "statut_final": statut}


def main() -> int:
    res = jouer()
    for c in res["cas"]:
        print(f"[{'OK' if c['ok'] else 'ÉCHEC'}] {c['cas']}" + (f" — {c['detail']}" if c['detail'] else ""))
    reussis = sum(c["ok"] for c in res["cas"])
    verdict = "OK" if reussis == len(res["cas"]) else "ECHEC"
    print(f"\n{reussis}/{len(res['cas'])} cas — {'TOUT EST OK' if verdict == 'OK' else 'ÉCHEC'}")
    ecrire(os.path.join(DOSSIER, "guard_evidence.json"), module="agent_guard", phase=3,
           etiquette="VÉRIFIÉ", verdict=verdict,
           config={"allowlist": ["example.com", "neverssl.com", "info.cern.ch"], "corps_max": 1024 * 1024,
                   "origine": "serveur HTTP local se faisant passer pour les hôtes autorisés"},
           mesures={"cas": res["cas"], "reussis": reussis, "statut_api": res["statut_final"]},
           limites=["Trafic HTTP vers les trois hôtes publics NON joué : le proxy sortant de "
                    "l'environnement ne relaie que le HTTPS. L'origine est locale ; le code de "
                    "décision, de relais et de journalisation est celui de production.",
                    "Mono-machine, pas de consensus ; les réponses ne sont pas inspectées : une "
                    "destination autorisée compromise reste un risque.",
                    "Couverture limitée au trafic qui passe effectivement par le GARDIEN.",
                    "Heuristiques de canaux cachés : signaux, jamais preuves."])
    return 0 if verdict == "OK" else 1


if __name__ == "__main__":
    sys.exit(main())
