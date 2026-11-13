import math
import random
import unittest

from telegraphe import afsk, trame


class NRZI(unittest.TestCase):
    def test_nrzi_reversible(self):
        bits = [0, 1, 1, 0, 1, 0, 0, 1, 1, 1, 0]
        self.assertEqual(afsk._nrzi_inverse(afsk._nrzi(bits)), bits)

    def test_zero_bascule_un_maintient(self):
        self.assertEqual(afsk._nrzi([1, 1, 1], ton_initial=1), [1, 1, 1])
        self.assertEqual(afsk._nrzi([0, 0, 0], ton_initial=1), [0, 1, 0])


class Modem(unittest.TestCase):
    def setUp(self):
        self.msg = "OMEGA-HERMÈS — graine 7.".encode("utf-8")
        self.bits = trame.construire(self.msg)
        self.ech = afsk.moduler(self.bits)

    def test_aller_retour_exact_en_memoire(self):
        recu = trame.analyser(afsk.demoduler(self.ech, len(self.bits)))
        self.assertEqual(recu, self.msg)

    def test_aller_retour_exact_via_wav(self):
        octets = afsk.vers_wav_octets(self.ech)
        ech2, fs = afsk.depuis_wav_octets(octets)
        self.assertEqual(fs, afsk.FS)
        self.assertEqual(trame.analyser(afsk.demoduler(ech2, len(self.bits))), self.msg)

    def test_signal_borne(self):
        self.assertTrue(all(-1.0 <= x <= 1.0 for x in self.ech))

    def test_duree_coherente(self):
        # ~ nb de bits / baud, à un bit près (bornes d'échantillon arrondies).
        attendue = len(self.bits) / afsk.BAUD
        mesuree = len(self.ech) / afsk.FS
        self.assertAlmostEqual(mesuree, attendue, delta=1 / afsk.BAUD)

    def test_bruit_blanc_fort_corrompt_puis_le_crc_rejette(self):
        # Corruption franche : on écrase une rafale d'échantillons par du bruit.
        # Le modem peut mal lire des bits ; le CRC doit alors refuser la trame,
        # jamais livrer des octets faux en silence.
        rnd = random.Random(7)
        rejets = faux = bons = 0
        for essai in range(40):
            ech = list(self.ech)
            debut = rnd.randrange(0, len(ech) - 400)
            for i in range(debut, debut + 400):
                ech[i] = rnd.uniform(-1, 1)
            try:
                recu = trame.analyser(afsk.demoduler(ech, len(self.bits)))
                if recu == self.msg:
                    bons += 1
                else:
                    faux += 1
            except trame.TrameInvalide:
                rejets += 1
        # Aucune livraison d'octets faux : soit le bon message, soit un refus net.
        self.assertEqual(faux, 0, "le CRC a laissé passer des octets corrompus")
        self.assertGreater(rejets, 0, "la corruption n'a jamais été détectée")

    def test_goertzel_selectif(self):
        # Une sinusoïde pure à 1200 Hz : énergie mark ≫ énergie space.
        n = round(afsk.echantillons_par_bit())
        pur = [math.sin(2 * math.pi * afsk.F_MARK * i / afsk.FS) for i in range(n)]
        self.assertGreater(afsk._goertzel(pur, afsk.F_MARK, afsk.FS),
                           10 * afsk._goertzel(pur, afsk.F_SPACE, afsk.FS))


if __name__ == "__main__":
    unittest.main()
