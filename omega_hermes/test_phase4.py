import contextlib
import io
import json
import os
import tempfile
import unittest

import numpy as np

from omega_hermes import guardian
from omega_hermes.ai_mode import decider
from omega_hermes.alice import Alice
from omega_hermes.phase4 import executer
from omega_hermes.twin import Twin


class Phase4(unittest.TestCase):
    def test_sept_modules_tous_les_criteres(self):
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()):
            code = executer(dossier=tmp)
            docs = {f: json.load(open(os.path.join(tmp, f))) for f in os.listdir(tmp)}
        self.assertEqual(len(docs), 7)
        echecs = {f: [c for c in d["mesures"]["criteres"] if not c["ok"]] for f, d in docs.items()}
        self.assertEqual(code, 0, echecs)
        self.assertTrue(all(d["etiquette"] == "SIMULÉ" for d in docs.values()))


class Unitaires(unittest.TestCase):
    def test_lot_de_taille_exacte(self):
        al = Alice(Twin(7), 7)
        for n in (1, 7, 30, 199, 200, 333):
            self.assertEqual(len(al.lot(n)[1]), n)

    def test_politique_ia_unknown_toujours_en_quarantaine(self):
        self.assertEqual(decider("UNKNOWN", True, 1e4, 60)[0], "QUARANTAINE")   # piège du §4.3
        self.assertEqual(decider("ARTIFACT", True, 80, 60)[0], "SIGNALER")
        self.assertEqual(decider("ARTIFACT", False, 80, 60)[0], "QUARANTAINE")
        self.assertEqual(decider("REPOS", False, 20, 60)[0], "ACCEPTER")

    def test_guardian_refuse_tout_contenu(self):
        for e in ({"categorie": "lettre", "t_appui_ms": 0, "t_relache_ms": 1, "caractere": "a"},
                  {"categorie": "a", "t_appui_ms": 0, "t_relache_ms": 1},
                  {"categorie": "lettre", "t_appui_ms": 5, "t_relache_ms": 1}):
            with self.assertRaises(guardian.EvenementRefuse):
                guardian.analyser([e] * 12)

    def test_guardian_seuil_depend_de_la_longueur(self):
        rng = np.random.default_rng(0)
        court = guardian.analyser(guardian.synthetique(rng, "humain", 20))
        long_ = guardian.analyser(guardian.synthetique(rng, "humain", 400))
        self.assertGreater(court["seuil_effacement"], long_["seuil_effacement"])


if __name__ == "__main__":
    unittest.main()
