import unittest

import numpy as np

from omega_hermes.alice import ARTIFACT, UNKNOWN, Alice
from omega_hermes.bob import Bob, plateaux
from omega_hermes.eyes import Standardiseur, traits
from omega_hermes.twin import CLASSES, Twin


def banc(regle):
    twin = Twin(7)
    classes = [CLASSES[i % 3] for i in range(450)]
    X = twin.lot(classes)
    std = Standardiseur().ajuster(traits(X))
    return Bob(regle=regle).entrainer(std.transformer(traits(X)), classes), std, Alice(twin, 7)


class DefautHistorique(unittest.TestCase):
    """§12 phase 2 : reproduire d'abord le défaut, puis la correction."""

    def carres(self, alice, n=30):
        rng = np.random.default_rng(11)
        return np.stack([alice.carre(rng) for _ in range(n)])

    def test_1_seuil_unique_classe_les_carres_artifact(self):
        bob, std, alice = banc("seuil_unique")
        X = self.carres(alice)
        decisions, _ = bob.decider(X, std.transformer(traits(X)))
        self.assertGreater(decisions.count(ARTIFACT) / len(X), 0.9)   # bon score, mauvaise raison

    def test_2_deux_seuils_les_classe_unknown(self):
        bob, std, alice = banc("deux_seuils")
        X = self.carres(alice)
        decisions, dmin = bob.decider(X, std.transformer(traits(X)))
        self.assertEqual(set(decisions), {UNKNOWN})
        self.assertTrue((dmin >= bob.seuil_lache).all())


class Regle(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bob, cls.std, cls.alice = banc("deux_seuils")

    def test_seuils(self):
        self.assertAlmostEqual(self.bob.seuil_lache, 100 * self.bob.seuil_strict)
        frac = (self.bob.distances_entrainement > self.bob.seuil_strict).mean()
        self.assertAlmostEqual(frac, 0.01, delta=0.005)

    def test_connu_propre_classe_correctement(self):
        X = self.alice.twin.lot(["REPOS", "CHARGE", "RESONANCE"] * 10)
        decisions, _ = self.bob.decider(X, self.std.transformer(traits(X)))
        bons = sum(d == c for d, c in zip(decisions, ["REPOS", "CHARGE", "RESONANCE"] * 10))
        self.assertGreaterEqual(bons, 28)

    def test_artefact_a_faible_distance_reste_artifact(self):
        rng = np.random.default_rng(5)
        x = self.alice.dropout(self.alice.twin.observer("CHARGE"), rng)
        self.assertTrue(plateaux(x)[0])
        self.assertEqual(self.bob.decider(x[None], self.std.transformer(traits(x)))[0], [ARTIFACT])

    def test_regle_inconnue_refusee(self):
        with self.assertRaises(ValueError):
            Bob(regle="magique")


if __name__ == "__main__":
    unittest.main()
