import hashlib
import os
import tempfile
import unittest

import numpy as np

from omega_hermes import decouplage
from omega_hermes.alice import LABELS, MIX_200, Alice
from omega_hermes.twin import CLASSES, MODALITES, N, Twin


class Jumeau(unittest.TestCase):
    def test_forme_et_determinisme(self):
        a, b = Twin(7).observer("CHARGE"), Twin(7).observer("CHARGE")
        self.assertEqual(a.shape, (len(MODALITES), N))
        np.testing.assert_array_equal(a, b)
        self.assertFalse(np.array_equal(a, Twin(8).observer("CHARGE")))

    def test_jamais_un_signal_repete(self):
        tw = Twin(7)
        empreintes = {hashlib.sha256(tw.observer(CLASSES[i % 3]).tobytes()).hexdigest()
                      for i in range(600)}
        self.assertEqual(len(empreintes), 600)

    def test_flux_alice_independant_du_jumeau(self):
        tw = Twin(7)
        Alice(tw, 7).lot(20)
        np.testing.assert_array_equal(Twin(7).observer("REPOS"),
                                      Twin(7).observer("REPOS"))


class Alice_(unittest.TestCase):
    def test_composition_du_lot(self):
        _, labels, familles = Alice(Twin(7), 7).lot(200)
        self.assertEqual(len(labels), 200)
        attendu = {}
        for label, famille, n in MIX_200:
            attendu[famille] = attendu.get(famille, 0) + n
        self.assertEqual({f: familles.count(f) for f in attendu}, attendu)
        self.assertTrue(set(labels) <= set(LABELS))

    def test_covert_synchronise_draft_decouple(self):
        al = Alice(Twin(7), 7)
        x = al.twin.observer("REPOS")
        rng = np.random.default_rng(1)
        c = al.covert(x, rng) - x
        d = al.draft(x, rng) - x
        t, e = MODALITES.index("temporel"), MODALITES.index("electrique")
        np.testing.assert_allclose(c[t], c[e], atol=1e-12)  # même phase
        self.assertGreater(c[t].max(), 0)
        self.assertEqual(np.abs(d[t]).max(), 0)            # le temporel reste nominal
        self.assertGreater(d[e].max(), 0)


class Decouplage(unittest.TestCase):
    def test_banc_sans_violation(self):
        self.assertEqual(decouplage.violations(), [])

    def test_detecte_les_acces_au_reel(self):
        with tempfile.TemporaryDirectory() as tmp:
            chemin = os.path.join(tmp, "fautif.py")
            with open(chemin, "w") as fh:
                fh.write("import socket\nfrom urllib import request\nimport numpy as np\n"
                         "x = np.load('capteur.npy')\nopen('/dev/ttyUSB0')\n")
            motifs = [v["motif"] for v in decouplage.violations([chemin])]
        self.assertEqual(motifs, ["import socket", "from urllib import", "attribut .load",
                                  "appel open()"])


if __name__ == "__main__":
    unittest.main()
