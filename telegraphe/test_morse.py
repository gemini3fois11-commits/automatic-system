import random
import unittest

from telegraphe import morse


class CodeMorse(unittest.TestCase):
    def test_aller_retour_texte(self):
        for t in ["SOS", "OMEGA HERMES", "HELLO WORLD", "CQ DE F5OEG", "GRAINE 7."]:
            self.assertEqual(morse.decoder(morse.encoder(t)), t.upper())

    def test_caractere_hors_code(self):
        with self.assertRaises(morse.MorseInvalide):
            morse.encoder("café")  # « é » hors du code international

    def test_symbole_inconnu_rejete(self):
        with self.assertRaises(morse.MorseInvalide):
            morse.decoder("........")  # 8 points : aucune lettre


class Durees(unittest.TestCase):
    def test_aller_retour_propre(self):
        for t in ["SOS", "OMEGA HERMES", "THE QUICK BROWN FOX", "GRAINE 7."]:
            for unite in (1, 5, 40):
                ev = morse.vers_durees(t, unite=unite)
                self.assertEqual(morse.depuis_durees(ev), t.upper())

    def test_adaptatif_sous_gigue(self):
        # L'unité n'est pas donnée : elle est estimée. Gigue ±30 % par élément.
        rnd = random.Random(7)
        ok = total = 0
        for t in ["OMEGA HERMES", "SOS SOS", "THE QUICK BROWN FOX", "CQ DE F5OEG", "GRAINE 7."]:
            for unite in (4, 12, 50):
                ev = morse.vers_durees(t, unite=unite)
                marge = int(unite * 0.30)
                bruite = [(e, max(1, d + rnd.randint(-marge, marge))) for e, d in ev]
                total += 1
                ok += morse.depuis_durees(bruite) == t.upper()
        self.assertEqual(ok, total)

    def test_signal_vide(self):
        with self.assertRaises(morse.MorseInvalide):
            morse.depuis_durees([])


if __name__ == "__main__":
    unittest.main()
