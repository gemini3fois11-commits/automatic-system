import json
import os
import subprocess
import sys
import unittest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOSSIER = os.path.join(RACINE, "console")


class Console(unittest.TestCase):
    """Vérification finale de la phase 7 (blueprint §12) : HTML statique, 0 erreur console,
    aucun débordement mobile, tous les liens d'évidence existants."""

    @classmethod
    def setUpClass(cls):
        r = subprocess.run([sys.executable, "-m", "console.generer"], cwd=RACINE,
                           capture_output=True, text=True, timeout=60)
        assert r.returncode == 0, r.stderr
        r = subprocess.run(["node", os.path.join(DOSSIER, "verifier.js")], cwd=RACINE,
                           capture_output=True, text=True, timeout=120)
        cls.rc, cls.sortie = r.returncode, r.stdout
        cls.data = json.loads(r.stdout)

    def test_aucune_erreur_console_sur_les_deux_profils(self):
        self.assertEqual(self.data["desktop"]["erreurs"], [])
        self.assertEqual(self.data["mobile"]["erreurs"], [])

    def test_aucun_debordement_horizontal_a_375px(self):
        self.assertLessEqual(self.data["mobile"]["debordement_px"], 0)
        self.assertLessEqual(self.data["desktop"]["debordement_px"], 0)

    def test_tous_les_liens_d_evidence_existent(self):
        self.assertEqual(self.data["liens"]["manquants"], [])
        self.assertGreater(self.data["liens"]["internes"], 20)

    def test_mission_affichee_comme_proposee(self):
        texte = self.data["desktop"]["missionText"]
        self.assertIn("proposée", texte)
        self.assertIn("attente de confirmation", texte)

    def test_contient_tous_les_modules(self):
        self.assertGreaterEqual(self.data["desktop"]["modules"], 25)
        self.assertEqual(self.data["desktop"]["kpiLignes"], self.data["desktop"]["modules"])


if __name__ == "__main__":
    unittest.main()
