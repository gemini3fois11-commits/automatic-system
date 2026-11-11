import contextlib
import io
import os
import tempfile
import unittest

from outils.evidence import lire
from plateforme_omega.orchestrator import SUITES_BLUEPRINT, main


class Plateforme(unittest.TestCase):
    """Commande de vérification du §12 phase 5 : un cycle complet de la plateforme."""

    @classmethod
    def setUpClass(cls):
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "plateforme_evidence.json")
            with contextlib.redirect_stdout(io.StringIO()):
                cls.code = main(["--out", out])
            cls.doc = lire(out)
        cls.m = cls.doc["mesures"]

    def test_aucune_suite_en_echec(self):
        self.assertEqual([s["suite"] for s in self.m["suites"] if s["statut"] == "ECHEC"], [])

    def test_seules_les_suites_non_construites_sont_absentes(self):
        absentes = {s["suite"] for s in self.m["suites"] if s["statut"] == "ABSENTE"}
        self.assertLessEqual(absentes, {"rag", "pinning", "fusion"})
        self.assertGreaterEqual(self.m["blueprint"]["ok"] + len(absentes), len(SUITES_BLUEPRINT))

    def test_gain_parallele_mesure_comme_un_rapport(self):
        self.assertGreater(self.m["gain_parallele"], 1.0)
        self.assertAlmostEqual(self.m["gain_parallele"],
                               self.m["duree_sequentielle_estimee_s"] / self.m["duree_murale_s"])

    def test_omega_q_conforme_a_la_regle(self):
        self.assertGreaterEqual(len(self.m["omega_q"]), 17)
        for e in self.m["omega_q"]:
            attendu = "ACCEPTER" if e["Q"] > 0 else ("REVOIR" if e["Q"] == 0 else "REJETER")
            if "veto_attaquant" not in e["drapeaux"]:
                self.assertEqual(e["decision"], attendu, e)
            self.assertAlmostEqual(e["Q"], e["S"] + e["P"] + e["R"] - e["C"], places=5)
            self.assertGreater(e["loc"], 0, e["module"])

    def test_balayage_hermes_six_configurations(self):
        self.assertEqual(len(self.m["balayage_hermes"]), 6)
        self.assertTrue(all(b["rejet_inconnu"] == 1.0 for b in self.m["balayage_hermes"]))


if __name__ == "__main__":
    unittest.main()
