import random
import unittest

from telegraphe import afsk, micro, trame

MSG = "CQ DE OMEGA HERMES — graine 7.".encode("utf-8")


def _audio():
    return afsk.moduler(trame.construire(MSG))


class SyncAveugle(unittest.TestCase):
    def test_decalage_continu_gain_silence_sans_bruit(self):
        base = _audio()
        deg = micro.degrader(base, rng=random.Random(7), gain=0.4, continu=0.2,
                             silence_avant=137, silence_apres=90)
        octets, start = micro.recevoir_flux(deg)
        self.assertEqual(octets, MSG)
        self.assertGreater(start, 0)  # le silence de tête a bien été franchi

    def test_aucun_faux_positif_sur_bruit(self):
        # Le balayage lourd est dans banc_micro ; ici on garde juste le comportement.
        n = len(_audio())
        faux = 0
        for k in range(40):
            r = random.Random(k)
            try:
                micro.recevoir_flux([r.gauss(0, 1) for _ in range(n)])
                faux += 1
            except trame.TrameInvalide:
                pass
        self.assertEqual(faux, 0)

    def test_recuperation_a_6db(self):
        base = _audio()
        ok = 0
        for k in range(8):
            r = random.Random(100 + k)
            d = micro.degrader(base, rng=r, snr_db=6.0, gain=r.uniform(0.4, 1.0),
                               continu=r.uniform(-0.1, 0.1),
                               silence_avant=r.randint(0, 300), silence_apres=r.randint(0, 150))
            try:
                got, _ = micro.recevoir_flux(d)
                ok += got == MSG
            except trame.TrameInvalide:
                pass
        self.assertEqual(ok, 8)

    def test_flux_vide_et_silence(self):
        with self.assertRaises(trame.TrameInvalide):
            micro.recevoir_flux([])
        with self.assertRaises(trame.TrameInvalide):
            micro.recevoir_flux([0.0] * 5000)

    def test_onset_bande_ignore_le_continu(self):
        # Un niveau continu pur n'allume pas la bande : l'onset le saute.
        base = _audio()
        deg = [0.5] * 400 + base  # 400 échantillons de continu franc
        sig = micro._normaliser(micro._sans_continu(deg))
        self.assertGreater(micro._debut_bande(sig, afsk.FS / afsk.BAUD, afsk.FS), 200)


if __name__ == "__main__":
    unittest.main()
