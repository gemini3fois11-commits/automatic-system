"""Terminal authentifié — la démo propre (blueprint §5.2).

127.0.0.1:8076, bibliothèque standard, page sans CDN. Sans session : 401, et
GET /api/exec n'exécute jamais. Les commandes passent une allowlist stricte avec
une politique d'arguments par commande, shell=False, délai 5 s, sortie plafonnée à
64 Ko, répertoire de travail = bac à sable. Chaque événement entre dans une chaîne Γ.

Tant que le propriétaire n'a pas choisi son mot de passe sur la page, le terminal
reste en SETUP_MODE.

  python3 -m terminal_auth.server [--etat DOSSIER]
"""

import argparse
import os
import re
import selectors
import shlex
import signal
import subprocess
import sys
import time

from socle_preuve.auth import SESSION_S, Authentificateur, ErreurAuth
from socle_preuve.gamma import Chaine, lire_blocs, verifier_chaine
from socle_preuve.porte_http import Gestionnaire, Serveur

DOSSIER = os.path.dirname(os.path.abspath(__file__))
PORT = 8076
DELAI_S = 5
SORTIE_MAX = 64 * 1024
CODES_AUTH = {"setup_mode": 403, "verrouille": 403, "identifiants_invalides": 401,
              "mot_de_passe_trop_court": 400, "deja_configure": 409}
CHEMIN_RELATIF = re.compile(r"^(?!/)(?!.*(^|/)\.\.(/|$))[\w.\-/]+$")
FICHIERS_STATIQUES = {"/": ("terminal.html", "text/html; charset=utf-8"),
                      "/terminal.js": ("terminal.js", "text/javascript; charset=utf-8"),
                      "/terminal.css": ("terminal.css", "text/css; charset=utf-8")}


def _options(*autorisees):
    return lambda args: all(a in autorisees for a in args)


# Politique par commande : l'allowlist porte aussi sur les arguments.
POLITIQUE = {
    "echo": lambda args: True,
    "date": lambda args: all(re.fullmatch(r"\+[%A-Za-z:\-_ ]{1,40}|-u|-I", a) for a in args),
    "pwd": _options(),
    "whoami": _options(),
    "uname": _options("-a", "-s", "-r", "-m", "-n"),
    "ls": lambda args: all(a in ("-l", "-a", "-la", "-al", "-1") or CHEMIN_RELATIF.match(a)
                           for a in args),
}
INTERNES = ("help", "omega-statut")


def executer_borne(argv, cwd) -> tuple[int, bytes, bool]:
    """Exécute sans shell en lisant la sortie en flux : au-delà de SORTIE_MAX octets ou
    de DELAI_S secondes, le groupe de processus est tué. La mémoire reste bornée,
    quelle que soit la quantité que la commande écrit."""
    p = subprocess.Popen(argv, shell=False, cwd=cwd, stdin=subprocess.DEVNULL,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"}, start_new_session=True)
    fin = time.monotonic() + DELAI_S
    morceaux, total, tronque, delai = [], 0, False, False
    with selectors.DefaultSelector() as sel:
        sel.register(p.stdout, selectors.EVENT_READ)
        while True:
            reste = fin - time.monotonic()
            if reste <= 0 or not sel.select(reste):
                delai = True
                break
            bloc = os.read(p.stdout.fileno(), 65536)
            if not bloc:
                break
            morceaux.append(bloc)
            total += len(bloc)
            if total > SORTIE_MAX:
                tronque = True
                break
    if not (tronque or delai):
        # Fin de fichier atteinte : le processus se termine. Sous charge, il peut avoir fermé sa
        # sortie sans être encore sorti ; on l'attend dans le délai restant au lieu de le tuer.
        try:
            p.wait(timeout=max(0.0, fin - time.monotonic()))
        except subprocess.TimeoutExpired:
            delai = True
    if p.poll() is None:
        os.killpg(p.pid, signal.SIGKILL)
    p.wait()
    p.stdout.close()
    sortie = b"".join(morceaux)[:SORTIE_MAX]
    if delai:
        return 124, sortie + b"\n[delai_depasse]\n", tronque
    return p.returncode, sortie, tronque


class Terminal:
    def __init__(self, etat: str, *, delai_echec=0.5):
        os.makedirs(etat, mode=0o700, exist_ok=True)
        self.bac_a_sable = os.path.join(etat, "sandbox")
        os.makedirs(self.bac_a_sable, mode=0o700, exist_ok=True)
        self.journal = Chaine(os.path.join(etat, "audit.jsonl"))
        self.auth = Authentificateur(os.path.join(etat, "auth.json"), delai_echec=delai_echec,
                                     evenement=lambda t, d: self.journal.inscrire("auth", t, t, d))

    def executer(self, ligne: str) -> tuple[int, dict]:
        try:
            argv = shlex.split(ligne) if isinstance(ligne, str) else []
        except ValueError:
            argv = []
        if not argv or len(ligne) > 1024:
            return self._refus(ligne, "commande_illisible")
        nom, args = argv[0], argv[1:]
        if nom == "help":
            return self._ok(argv, 0, "Commandes : " + " ".join(sorted(POLITIQUE) + list(INTERNES)) + "\n")
        if nom == "omega-statut":
            return self._ok(argv, 0, f"journal d'audit : {verifier_chaine(self.journal.chemin)}\n")
        if nom not in POLITIQUE:
            return self._refus(ligne, "commande_non_autorisee")
        if not POLITIQUE[nom](args):
            return self._refus(ligne, "arguments_non_autorises")
        try:
            code, sortie, tronque = executer_borne(argv, self.bac_a_sable)
        except OSError:
            return self._refus(ligne, "commande_introuvable")
        texte = sortie.decode("utf-8", "replace") + ("\n[sortie_tronquee]\n" if tronque else "")
        return self._ok(argv, code, texte)

    def _ok(self, argv, code, texte):
        self.journal.inscrire("exec", "EXECUTE", "allowlist", {"argv": [a[:200] for a in argv[:20]],
                                                               "code_retour": code})
        return 200, {"code_retour": code, "sortie": texte}

    def _refus(self, ligne, raison):
        self.journal.inscrire("exec", "REFUS", raison, {"ligne": str(ligne)[:200]})
        return 403, {"refus": raison}


class Gestion(Gestionnaire):
    server_version = "omega-terminal"

    @property
    def t(self) -> Terminal:
        return self.server.terminal

    def do_GET(self):
        if not self.controle_hote():
            return
        if self.path in FICHIERS_STATIQUES:
            nom, type_ = FICHIERS_STATIQUES[self.path]
            with open(os.path.join(DOSSIER, nom), "rb") as fh:
                self.envoyer(200, fh.read(), type_)
        elif self.path == "/api/etat":
            self.repondre_json(200, {"setup_mode": self.t.auth.setup_mode,
                                     "session": self.t.auth.valider(self.jeton())})
        elif self.path.startswith("/api/exec"):
            # Jamais d'exécution sur GET, avec ou sans session.
            code = 405 if self.t.auth.valider(self.jeton()) else 401
            self.repondre_json(code, {"erreur": "methode_refusee" if code == 405 else "non_authentifie"})
        elif self.path == "/api/audit":
            if not self.t.auth.valider(self.jeton()):
                self.repondre_json(401, {"erreur": "non_authentifie"})
                return
            blocs, rapport = lire_blocs(self.t.journal.chemin)
            self.repondre_json(200, {"integre": rapport.integre, "derniers": blocs[-50:]})
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
                if not self.t.auth.setup_mode:
                    raise ErreurAuth("deja_configure")
                self.t.auth.configurer(corps.get("mot_de_passe"))
                self.repondre_json(200, {"setup": "ok"})
            elif self.path == "/api/login":
                jeton = self.t.auth.connecter(corps.get("mot_de_passe"))
                self.repondre_json(200, {"session": "ouverte"}, self.cookie_session(jeton, SESSION_S))
            elif self.path == "/api/logout":
                self.t.auth.deconnecter(self.jeton())
                self.repondre_json(200, {"session": "fermee"}, self.cookie_efface())
            elif self.path == "/api/exec":
                if not self.t.auth.valider(self.jeton()):
                    self.repondre_json(401, {"erreur": "non_authentifie"})
                    return
                self.repondre_json(*self.t.executer(corps.get("commande")))
            else:
                self.repondre_json(404, {"erreur": "introuvable"})
        except ErreurAuth as e:
            self.repondre_json(CODES_AUTH.get(e.code, 400), {"erreur": e.code})


def construire(port=PORT, etat=None, **options) -> Serveur:
    terminal = Terminal(etat or os.path.join(DOSSIER, "etat"), **options)
    serveur = Serveur(port, Gestion)
    serveur.terminal = terminal
    return serveur


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python3 -m terminal_auth.server")
    ap.add_argument("--port", type=int, default=PORT)
    ap.add_argument("--etat", default=os.path.join(DOSSIER, "etat"))
    a = ap.parse_args(argv)
    s = construire(a.port, a.etat)
    print(f"Terminal sur http://127.0.0.1:{a.port} — "
          f"{'SETUP_MODE : le propriétaire choisit son mot de passe sur la page' if s.terminal.auth.setup_mode else 'configuré'}")
    try:
        s.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        s.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
