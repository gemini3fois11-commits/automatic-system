"""Runtime supervisé V8.1 (blueprint §5.3) : faire tourner un service sans surprise.

- Verrou flock : un second superviseur est refusé (code de sortie 2).
- Relance bornée : attentes 1, 2, 4, 8, 8 s ; au plus 5 relances, puis abandon (code 1).
- SIGTERM / SIGINT : arrêt propre du groupe de processus du service, code 0, aucun survivant.
- Registre atomique (écriture puis rename) ; avant de signaler un PID hérité, son identité
  est vérifiée par /proc/<pid>/cmdline : un PID recyclé n'est jamais tué.
- Chaque événement entre dans une chaîne Γ. Rien n'est écrit hors du dossier d'état :
  ni ~/.bashrc, ni crontab, ni service système. Aucune persistance cachée.

  python3 -m runtime.superviseur --etat DOSSIER -- commande arguments…
"""

import argparse
import fcntl
import json
import os
import signal
import subprocess
import sys
import time

from socle_preuve.gamma import Chaine

ATTENTES_S = (1, 2, 4, 8)
RELANCES_MAX = 5
GRACE_ARRET_S = 5


def cmdline(pid: int) -> list[str] | None:
    try:
        with open(f"/proc/{pid}/cmdline", "rb") as fh:
            brut = fh.read()
    except (FileNotFoundError, ProcessLookupError, PermissionError):
        return None
    return [a.decode("utf-8", "replace") for a in brut.split(b"\0") if a] or None


def ecrire_atomique(chemin: str, objet) -> None:
    tmp = f"{chemin}.{os.getpid()}.tmp"
    with open(os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w") as fh:
        json.dump(objet, fh)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, chemin)


class Superviseur:
    def __init__(self, commande: list[str], etat: str, *, facteur_temps: float = 1.0):
        if not commande:
            raise ValueError("commande vide")
        self.commande, self.etat, self.facteur = list(commande), etat, facteur_temps
        os.makedirs(etat, mode=0o700, exist_ok=True)
        self.registre = os.path.join(etat, "registre.json")
        self.journal = Chaine(os.path.join(etat, "runtime.jsonl"))
        self._arret = False

    def _noter(self, decision, raison, **donnees):
        self.journal.inscrire("runtime", decision, raison, donnees)

    def _attendre(self, secondes: float) -> None:
        fin = time.monotonic() + secondes * self.facteur
        while not self._arret and time.monotonic() < fin:
            time.sleep(min(0.02, max(0.0, fin - time.monotonic())))

    def _terminer(self, pid: int) -> None:
        try:
            os.killpg(pid, signal.SIGTERM)
        except ProcessLookupError:
            return
        fin = time.monotonic() + GRACE_ARRET_S * self.facteur
        while time.monotonic() < fin:
            try:
                os.killpg(pid, 0)
            except ProcessLookupError:
                return
            time.sleep(0.02)
        try:
            os.killpg(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass

    def _orphelin(self) -> None:
        try:
            with open(self.registre) as fh:
                ancien = json.load(fh)
        except (FileNotFoundError, ValueError):
            return
        pid, attendue = ancien.get("pid"), ancien.get("cmdline")
        actuelle = cmdline(pid) if isinstance(pid, int) else None
        if actuelle is None:
            self._noter("REGISTRE", "orphelin_absent", pid=pid)
        elif actuelle == attendue:
            self._terminer(pid)
            self._noter("ARRET", "orphelin_termine", pid=pid)
        else:
            self._noter("REGISTRE", "pid_recycle_ignore", pid=pid)   # identité différente : on n'y touche pas
        os.remove(self.registre)

    def executer(self) -> int:
        verrou = os.open(os.path.join(self.etat, "superviseur.lock"), os.O_RDWR | os.O_CREAT, 0o600)
        try:
            fcntl.flock(verrou, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("superviseur_deja_actif", file=sys.stderr)
            os.close(verrou)
            return 2
        precedents = {s: signal.signal(s, self._signal) for s in (signal.SIGTERM, signal.SIGINT)}
        try:
            return self._boucle()
        finally:
            for s, h in precedents.items():
                signal.signal(s, h)
            os.close(verrou)

    def _signal(self, signum, frame):
        self._arret = True

    def _boucle(self) -> int:
        self._orphelin()
        relances = 0
        while not self._arret:
            enfant = subprocess.Popen(self.commande, start_new_session=True, stdin=subprocess.DEVNULL)
            # On enregistre la commande lancée, pas cmdline(pid) : juste après le fork l'enfant
            # n'a pas toujours fini son exec, et /proc rendrait une valeur vide. L'identité d'un
            # orphelin se vérifie ensuite en comparant cette commande au cmdline(pid) relu au
            # redémarrage, qui vaut bien self.commande une fois l'exec faite.
            ecrire_atomique(self.registre, {"pid": enfant.pid, "cmdline": self.commande,
                                            "relances": relances, "demarre": time.time()})
            self._noter("DEMARRAGE", "service_lance", pid=enfant.pid, relances=relances)
            while enfant.poll() is None and not self._arret:
                time.sleep(0.02)
            if self._arret:
                self._terminer(enfant.pid)
                enfant.wait()
                self._noter("ARRET", "signal_recu", pid=enfant.pid)
                os.remove(self.registre)
                return 0
            code = enfant.returncode
            self._noter("SORTIE", "service_termine" if code == 0 else "service_en_echec",
                        pid=enfant.pid, code=code)
            if code == 0:
                os.remove(self.registre)
                return 0
            if relances >= RELANCES_MAX:
                self._noter("ABANDON", "relances_epuisees", relances=relances)
                os.remove(self.registre)
                return 1
            attente = ATTENTES_S[min(relances, len(ATTENTES_S) - 1)]
            relances += 1
            self._noter("RELANCE", "attente_bornee", attente_s=attente, relance=relances)
            self._attendre(attente)
        return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python3 -m runtime.superviseur")
    ap.add_argument("--etat", required=True)
    ap.add_argument("--facteur-temps", type=float, default=1.0, help="accélère les attentes (tests)")
    ap.add_argument("commande", nargs=argparse.REMAINDER)
    a = ap.parse_args(argv)
    commande = a.commande[1:] if a.commande[:1] == ["--"] else a.commande
    return Superviseur(commande, a.etat, facteur_temps=a.facteur_temps).executer()


if __name__ == "__main__":
    sys.exit(main())
