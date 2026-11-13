import fcntl
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
import unittest

from runtime.superviseur import Superviseur as SuperviseurProc
from runtime.superviseur import cmdline, ecrire_atomique, main
from socle_preuve.gamma import lire_blocs

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def fermer_proc(p: subprocess.Popen) -> None:
    """Arrête, attend et ferme les tubes d'un processus de test.

    p.wait() seul ne ferme pas les BufferedReader de stdout/stderr : non fermés, ils
    déclenchent un ResourceWarning au ramasse-miettes, fatal sous `python -W error`
    (l'orchestrateur lance cette suite ainsi). On ferme donc les tubes explicitement.
    """
    try:
        if p.poll() is None:
            p.kill()
        p.wait(timeout=10)
    finally:
        for flux in (p.stdin, p.stdout, p.stderr):
            if flux is not None:
                flux.close()


class Superviseur(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.etat = os.path.join(self.tmp.name, "etat")
        self.lances = []

    def tearDown(self):
        for p in self.lances:
            fermer_proc(p)

    def lancer(self, *commande, facteur=0.01):
        p = subprocess.Popen([sys.executable, "-m", "runtime.superviseur", "--etat", self.etat,
                              "--facteur-temps", str(facteur), "--", *commande], cwd=RACINE,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.lances.append(p)
        return p

    def attendre_registre(self):
        chemin = os.path.join(self.etat, "registre.json")
        fin = time.monotonic() + 10
        while time.monotonic() < fin:
            try:
                with open(chemin) as fh:
                    return json.load(fh)
            except (FileNotFoundError, ValueError):
                time.sleep(0.02)
        self.fail("registre jamais écrit")

    def journal(self):
        return lire_blocs(os.path.join(self.etat, "runtime.jsonl"))[0]

    def attendre_cmdline(self, pid, attendu, delai=10):
        """Attend que /proc/<pid>/cmdline reflète l'exec (fenêtre fork→exec sous charge)."""
        fin = time.monotonic() + delai
        while time.monotonic() < fin and cmdline(pid) != attendu:
            time.sleep(0.02)
        self.assertEqual(cmdline(pid), attendu)

    def test_second_superviseur_refuse(self):
        self.lancer("sleep", "30")
        self.attendre_registre()
        second = self.lancer("sleep", "30")
        self.assertEqual(second.wait(timeout=10), 2)
        self.assertIn(b"superviseur_deja_actif", second.stderr.read())

    def test_relances_bornees_puis_abandon(self):
        p = self.lancer("false")
        self.assertEqual(p.wait(timeout=30), 1)
        blocs = self.journal()
        attentes = [b["donnees"]["attente_s"] for b in blocs if b["decision"] == "RELANCE"]
        self.assertEqual(attentes, [1, 2, 4, 8, 8])
        self.assertEqual(sum(b["decision"] == "DEMARRAGE" for b in blocs), 6)
        self.assertEqual(blocs[-1]["raison"], "relances_epuisees")

    def test_sigterm_arret_propre_sans_survivant(self):
        p = self.lancer("sleep", "60", facteur=1.0)
        registre = self.attendre_registre()
        self.assertEqual(registre["cmdline"], ["sleep", "60"])
        self.attendre_cmdline(registre["pid"], ["sleep", "60"])
        p.send_signal(signal.SIGTERM)
        self.assertEqual(p.wait(timeout=10), 0)
        self.assertIsNone(cmdline(registre["pid"]))
        self.assertFalse(os.path.exists(os.path.join(self.etat, "registre.json")))
        self.assertEqual(self.journal()[-1]["raison"], "signal_recu")

    def test_service_termine_normalement(self):
        self.assertEqual(self.lancer("true").wait(timeout=10), 0)
        self.assertEqual([b["raison"] for b in self.journal()], ["service_lance", "service_termine"])

    def test_pid_recycle_jamais_tue(self):
        os.makedirs(self.etat, exist_ok=True)
        temoin = subprocess.Popen(["sleep", "30"])
        self.lances.append(temoin)
        ecrire_atomique(os.path.join(self.etat, "registre.json"),
                        {"pid": temoin.pid, "cmdline": ["autre", "commande"]})
        self.assertEqual(self.lancer("true").wait(timeout=10), 0)
        self.assertIsNone(temoin.poll())                       # toujours vivant
        self.assertEqual(self.journal()[0]["raison"], "pid_recycle_ignore")

    def test_orphelin_identique_termine(self):
        os.makedirs(self.etat, exist_ok=True)
        orphelin = subprocess.Popen(["sleep", "31"], start_new_session=True)
        self.lances.append(orphelin)
        ecrire_atomique(os.path.join(self.etat, "registre.json"),
                        {"pid": orphelin.pid, "cmdline": ["sleep", "31"]})
        self.assertEqual(self.lancer("true").wait(timeout=10), 0)
        self.assertIsNotNone(orphelin.wait(timeout=5))
        self.assertEqual(self.journal()[0]["raison"], "orphelin_termine")

    def test_aucune_persistance_cachee(self):
        with open(os.path.join(RACINE, "runtime", "superviseur.py")) as fh:
            source = fh.read().lower()
        for motif in ("open(\"~", "expanduser", "crontab -", "systemctl", "/etc/init", "launchctl"):
            self.assertNotIn(motif, source)


class SuperviseurUnitaire(unittest.TestCase):
    """Pilote les méthodes du superviseur dans le processus de test.

    Les tests de bout en bout plus haut lancent le superviseur comme sous-processus :
    sa logique s'exécute donc hors de l'instrumentation de couverture. Ces tests-ci
    l'exercent en direct pour verrouiller les branches sensibles (pid recyclé, orphelin
    absent, registre corrompu, arrêt d'un pid mort, commande vide, verrou flock).
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.etat = os.path.join(self.tmp.name, "etat")
        self.vivants = []
        self.py0 = [sys.executable, "-c", ""]                       # sort 0 aussitôt
        self.py1 = [sys.executable, "-c", "raise SystemExit(1)"]    # sort 1 aussitôt

    def tearDown(self):
        for p in self.vivants:
            fermer_proc(p)

    def sup(self, commande, **kw):
        return SuperviseurProc(commande, self.etat, **kw)

    def sleep_isole(self, duree="30"):
        p = subprocess.Popen(["sleep", duree], start_new_session=True)
        self.vivants.append(p)
        # Attendre que l'enfant soit vraiment établi : setsid fait (pgid == pid, sinon un
        # killpg viserait un groupe inexistant) ET exec fait (cmdline rempli, sinon le
        # registre enregistrerait None et _orphelin ne reconnaîtrait pas l'orphelin). En
        # production l'orphelin lu au registre tourne depuis longtemps ; ce sas reproduit
        # cette condition et évite une course propre au test sous forte charge.
        attendu = ["sleep", duree]
        fin = time.monotonic() + 10
        while time.monotonic() < fin:
            try:
                if os.getpgid(p.pid) == p.pid and cmdline(p.pid) == attendu:
                    break
            except ProcessLookupError:
                break
            time.sleep(0.01)
        return p

    def journal(self):
        return lire_blocs(os.path.join(self.etat, "runtime.jsonl"))[0]

    def registre_absent(self):
        return not os.path.exists(os.path.join(self.etat, "registre.json"))

    def ecrire_registre(self, objet):
        os.makedirs(self.etat, mode=0o700, exist_ok=True)
        ecrire_atomique(os.path.join(self.etat, "registre.json"), objet)

    def test_commande_vide_refusee(self):
        with self.assertRaises(ValueError):
            self.sup([])

    def test_init_cree_le_dossier_d_etat_en_0700(self):
        s = self.sup(self.py0)
        self.assertTrue(os.path.isdir(self.etat))
        self.assertEqual(stat_mode(self.etat), 0o700)
        self.assertEqual(s.registre, os.path.join(self.etat, "registre.json"))

    def test_signal_demande_l_arret(self):
        s = self.sup(["jamais-execute"])
        self.assertFalse(s._arret)
        s._signal(signal.SIGTERM, None)
        self.assertTrue(s._arret)

    def test_attendre_dort_puis_retourne_vite_si_arret(self):
        s = self.sup(["jamais-execute"])
        t0 = time.monotonic()
        s._attendre(0.05)                                  # atteint la branche sleep
        self.assertGreaterEqual(time.monotonic() - t0, 0.03)
        s._arret = True
        t1 = time.monotonic()
        s._attendre(100)                                   # retour immédiat
        self.assertLess(time.monotonic() - t1, 1.0)

    def test_terminer_pid_inexistant_ne_leve_rien(self):
        self.sup(self.py0)._terminer(999_999_999)  # ProcessLookupError avalée

    def test_terminer_processus_vivant(self):
        cible = self.sleep_isole()
        self.sup(self.py0)._terminer(cible.pid)
        self.assertEqual(cible.wait(timeout=10), -signal.SIGTERM)

    def test_orphelin_sans_registre_ne_fait_rien(self):
        self.sup(self.py0)._orphelin()             # aucun registre : retour silencieux

    def test_orphelin_registre_corrompu_ignore(self):
        os.makedirs(self.etat, mode=0o700, exist_ok=True)
        with open(os.path.join(self.etat, "registre.json"), "w") as fh:
            fh.write("{ pas du json")
        self.sup(self.py0)._orphelin()             # ValueError avalée, pas de journal
        self.assertFalse(os.path.exists(os.path.join(self.etat, "runtime.jsonl"))
                         and any(self.journal()))

    def test_orphelin_pid_absent(self):
        self.ecrire_registre({"pid": 999_999_999, "cmdline": ["sleep", "30"]})
        self.sup(self.py0)._orphelin()
        self.assertEqual(self.journal()[0]["raison"], "orphelin_absent")
        self.assertTrue(self.registre_absent())

    def test_orphelin_pid_non_entier_est_absent(self):
        self.ecrire_registre({"pid": None, "cmdline": ["sleep", "30"]})
        self.sup(self.py0)._orphelin()
        self.assertEqual(self.journal()[0]["raison"], "orphelin_absent")

    def test_orphelin_identique_est_termine(self):
        cible = self.sleep_isole("31")
        self.ecrire_registre({"pid": cible.pid, "cmdline": cmdline(cible.pid)})
        self.sup(self.py0)._orphelin()
        self.assertIsNotNone(cible.wait(timeout=10))
        self.assertEqual(self.journal()[0]["raison"], "orphelin_termine")
        self.assertTrue(self.registre_absent())

    def test_orphelin_pid_recycle_jamais_tue(self):
        cible = self.sleep_isole()
        self.ecrire_registre({"pid": cible.pid, "cmdline": ["une", "autre", "commande"]})
        self.sup(self.py0)._orphelin()
        self.assertIsNone(cible.poll())                    # intact : identité différente
        self.assertEqual(self.journal()[0]["raison"], "pid_recycle_ignore")

    def test_boucle_succes_direct(self):
        self.assertEqual(self.sup(self.py0)._boucle(), 0)
        self.assertEqual([b["raison"] for b in self.journal()],
                         ["service_lance", "service_termine"])
        self.assertTrue(self.registre_absent())

    def test_boucle_echec_relances_bornees(self):
        self.assertEqual(self.sup(self.py1, facteur_temps=0.001)._boucle(), 1)
        blocs = self.journal()
        self.assertEqual([b["donnees"]["attente_s"] for b in blocs if b["decision"] == "RELANCE"],
                         [1, 2, 4, 8, 8])
        self.assertEqual(sum(b["decision"] == "DEMARRAGE" for b in blocs), 6)
        self.assertEqual(blocs[-1]["raison"], "relances_epuisees")
        self.assertTrue(self.registre_absent())

    def test_executer_verrou_acquis_puis_succes(self):
        avant = dict((s, signal.getsignal(s)) for s in (signal.SIGTERM, signal.SIGINT))
        self.assertEqual(self.sup(self.py0).executer(), 0)
        for s, h in avant.items():                         # handlers restaurés
            self.assertEqual(signal.getsignal(s), h)

    def test_executer_second_refuse_par_flock(self):
        self.sup(self.py0)                          # crée le dossier d'état
        tenu = os.open(os.path.join(self.etat, "superviseur.lock"), os.O_RDWR | os.O_CREAT, 0o600)
        try:
            fcntl.flock(tenu, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.assertEqual(self.sup(self.py0).executer(), 2)
        finally:
            os.close(tenu)

    def test_main_assemble_et_execute(self):
        rc = main(["--etat", self.etat, "--facteur-temps", "0.001", "--", *self.py0])
        self.assertEqual(rc, 0)
        self.assertEqual(self.journal()[-1]["raison"], "service_termine")


def stat_mode(chemin: str) -> int:
    return os.stat(chemin).st_mode & 0o777


if __name__ == "__main__":
    unittest.main()
