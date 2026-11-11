import os
import subprocess
import sys
import tempfile
import unittest

from cryoloop.banc import construire
from cryoloop.scenarios import CLE, SCENARIOS, jouer
from cryoloop.validateur import valider
from socle_preuve import ed25519
from socle_preuve.gamma import lire_blocs

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PUB = ed25519.cle_publique(CLE).hex()


class Matrice(unittest.TestCase):
    def test_chaque_scenario(self):
        for scenario in SCENARIOS:
            with self.subTest(scenario=scenario[0]):
                r = jouer(*scenario)
                self.assertTrue(r["ok"], r)
                self.assertTrue(all(r["invariants"].values()), r["invariants"])
                self.assertEqual(r["candidat"], r["decision"] == "ACCEPT")


class Proprietes(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.archive = os.path.join(self.tmp.name, "archive")
        construire(self.archive, cle=CLE)

    def test_deterministe(self):
        a = valider(self.archive, cle_publique=bytes.fromhex(PUB))
        b = valider(self.archive, cle_publique=bytes.fromhex(PUB))
        self.assertEqual((a.decision, a.archive_sha256, a.chaine), (b.decision, b.archive_sha256, b.chaine))

    def test_ne_cree_jamais_gamma(self):
        gamma = os.path.join(self.tmp.name, "absent.jsonl")
        valider(self.archive, gamma=gamma, cle_publique=bytes.fromhex(PUB))
        self.assertFalse(os.path.exists(gamma))

    def cli(self, *args):
        r = subprocess.run([sys.executable, "-m", "cryoloop", *args], cwd=RACINE,
                           capture_output=True, text=True, timeout=120)
        return r.returncode, r.stdout

    def test_codes_de_sortie_journal_et_candidat(self):
        journal = os.path.join(self.tmp.name, "cycles.jsonl")
        sortie = os.path.join(self.tmp.name, "candidats")
        code, out = self.cli("valider", self.archive, "--cle-publique", PUB,
                             "--journal", journal, "--sortie", sortie)
        self.assertEqual(code, 0, out)
        self.assertIn("LOOP 001", out)
        self.assertEqual(os.listdir(sortie), ["candidat-LOOP-001.json"])
        code, out = self.cli("valider", self.archive, "--journal", journal, "--sortie", sortie)
        self.assertEqual(code, 5, out)                                    # sans clé : PENDING
        self.assertIn("LOOP 002", out)
        self.assertEqual(os.listdir(sortie), ["candidat-LOOP-001.json"])  # pas de candidat
        blocs, rapport = lire_blocs(journal)
        self.assertTrue(rapport.integre)
        self.assertEqual([(b["decision"], b["raison"]) for b in blocs],
                         [("ACCEPT", "invariants_ok"), ("PENDING", "provenance_non_authentifiee")])
        self.assertEqual(self.cli("valider", os.path.join(self.tmp.name, "rien"))[0], 5)
        self.assertEqual(self.cli("valider", self.archive, "--cle-publique", PUB,
                                  "--perimetre", "DON-DC02")[0], 7)
        with open(os.path.join(self.archive, "mesures/E01.json"), "a") as fh:
            fh.write(" ")
        self.assertEqual(self.cli("valider", self.archive, "--cle-publique", PUB)[0], 6)
        self.assertEqual(self.cli("valider")[0], 2)


if __name__ == "__main__":
    unittest.main()
