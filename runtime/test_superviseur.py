import json
import os
import signal
import subprocess
import sys
import tempfile
import time
import unittest

from runtime.superviseur import cmdline, ecrire_atomique
from socle_preuve.gamma import lire_blocs

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class Superviseur(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.etat = os.path.join(self.tmp.name, "etat")
        self.lances = []

    def tearDown(self):
        for p in self.lances:
            if p.poll() is None:
                p.kill()
                p.wait()

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
        self.assertEqual(cmdline(registre["pid"]), ["sleep", "60"])
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


if __name__ == "__main__":
    unittest.main()
