import unittest

import numpy as np

from omega_hermes.alice import Alice
from omega_hermes.eyes import NOMS_TRAITS, Standardiseur, fft_radix2, traits
from omega_hermes.twin import Twin


class FFT(unittest.TestCase):
    def test_egale_numpy(self):
        rng = np.random.default_rng(7)
        for n in (1, 2, 8, 256):
            x = rng.normal(size=(3, n)) + 1j * rng.normal(size=(3, n))
            np.testing.assert_allclose(fft_radix2(x), np.fft.fft(x), atol=1e-10)

    def test_refuse_une_longueur_non_puissance_de_2(self):
        with self.assertRaises(ValueError):
            fft_radix2(np.zeros(100))


class Traits(unittest.TestCase):
    def test_31_traits(self):
        self.assertEqual(len(NOMS_TRAITS), 31)
        self.assertEqual(traits(Twin(7).lot(["REPOS", "CHARGE"])).shape, (2, 31))

    def test_frequence_dominante(self):
        t = np.arange(256)
        x = np.tile(np.sin(2 * np.pi * 20 * t / 256), (5, 1))
        self.assertAlmostEqual(traits(x)[0, 4], 20 / 128)

    def test_trait_31_separe_covert_du_nominal(self):
        al = Alice(Twin(7), 7)
        rng = np.random.default_rng(3)
        nominal = [traits(al.twin.observer("REPOS"))[0, -1] for _ in range(40)]
        covert = [traits(al.covert(al.twin.observer("REPOS"), rng))[0, -1] for _ in range(40)]
        self.assertLess(np.median(np.abs(nominal)), 0.05)
        self.assertGreater(np.median(covert), 0.15)

    def test_standardiseur(self):
        T = np.random.default_rng(0).normal(5, 3, (500, 31))
        Z = Standardiseur().ajuster(T).transformer(T)
        np.testing.assert_allclose(Z.mean(0), 0, atol=1e-12)
        np.testing.assert_allclose(Z.std(0), 1, atol=1e-12)


if __name__ == "__main__":
    unittest.main()
