import io
import contextlib
import json
import os
import tempfile
import unittest

from omega_hermes.hermes import mesurer
from omega_hermes.loop import main


class Metriques(unittest.TestCase):
    def test_definitions(self):
        labels = ["REPOS", "REPOS", "CHARGE", "ARTIFACT", "UNKNOWN", "COVERT", "DRAFT", "UNKNOWN"]
        decis = ["REPOS", "ARTIFACT", "REPOS", "ARTIFACT", "ARTIFACT", "UNKNOWN", "CHARGE", "UNKNOWN"]
        m = mesurer(labels, decis)
        self.assertAlmostEqual(m["fnr"], 1 / 3)            # REPOS rejeté
        self.assertAlmostEqual(m["fpr"], 1 / 5)            # DRAFT accepté comme CHARGE
        self.assertAlmostEqual(m["ber"], 3 / 6)            # nommables : 6, erreurs : 3
        self.assertEqual(m["rejet_inconnu"], 1.0)
        self.assertEqual(m["draft_rejection"], 0.0)
        c = m["composantes"]
        self.assertAlmostEqual(m["score"], 0.4 * c["1-BER"] + 0.4 * c["rejet_inconnu"] + 0.2 * c["1-FPR"])
        self.assertEqual(m["par_label"]["UNKNOWN"]["rappel"], 0.5)
        self.assertIsNone(m["par_label"]["COVERT"]["precision"])


class BouclePhase2(unittest.TestCase):
    """Commande de vérification du §12 phase 2, jouée en entier."""

    def test_boucle_200x5_graine_7(self):
        with tempfile.TemporaryDirectory() as tmp:
            ev = os.path.join(tmp, "e.json")
            with contextlib.redirect_stdout(io.StringIO()):
                code = main(["--evidence", ev, "--journal", os.path.join(tmp, "j.jsonl")])
            with open(ev, encoding="utf-8") as fh:
                doc = json.load(fh)
        echecs = [c for c in doc["mesures"]["criteres"] if not c["ok"]]
        self.assertEqual(code, 0, echecs)
        g = doc["mesures"]["global"]
        self.assertGreaterEqual(g["score"], 0.97)
        for cle in ("rejet_inconnu", "covert_rejection", "draft_rejection"):
            self.assertEqual(g[cle], 1.0)
        self.assertEqual(g["fpr"], 0.0)
        self.assertEqual(doc["etiquette"], "SIMULÉ")


if __name__ == "__main__":
    unittest.main()
