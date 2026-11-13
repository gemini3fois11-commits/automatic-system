import os
import tempfile
import unittest

from console import generer
from socle_preuve.gamma import verifier_chaine


class Generer(unittest.TestCase):
    def test_rendre_contient_les_cinq_sections(self):
        page = generer.rendre(generer.charger(), generer.chaine_echantillon())
        for ancre in ("id=\"hermes\"", "id=\"registre\"", "id=\"preuve\"",
                      "id=\"doc\"", "id=\"telegraphe\""):
            self.assertIn(ancre, page)

    def test_aucun_gabarit_non_rempli(self):
        page = generer.rendre(generer.charger(), generer.chaine_echantillon())
        # Pas de liste/dict Python recrachée telle quelle dans le HTML visible.
        self.assertNotIn("'ok': True", page)
        self.assertNotIn("'scenario'", page)

    def test_chaine_echantillon_est_reellement_scellee(self):
        lignes = generer.chaine_echantillon()
        self.assertGreaterEqual(len(lignes), 2)
        with tempfile.TemporaryDirectory() as d:
            chemin = os.path.join(d, "demo.jsonl")
            with open(chemin, "w", encoding="utf-8") as fh:
                fh.write("\n".join(lignes) + "\n")
            rap = verifier_chaine(chemin)
        # Ce que la page vérifie dans le navigateur est une vraie chaîne Γ intègre.
        self.assertTrue(rap.integre)
        self.assertEqual(rap.blocs, len(lignes))


if __name__ == "__main__":
    unittest.main()
