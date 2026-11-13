import itertools
import json
import os
import tempfile
import unittest

from socle_preuve.gamma import calculer_hash, verifier_chaine
from socle_preuve.temoin import ScelleurHMAC, verifier_temoin
from telegraphe import afsk, reception as R, trame


def _horloge():
    c = itertools.count()
    return lambda: f"2026-01-01T00:00:{next(c):02d}.000000Z"


class Reception(unittest.TestCase):
    def setUp(self):
        self.KA, self.KB = b"A" * 32, b"B" * 32
        self.secret = b"W" * 32
        self.dir = tempfile.TemporaryDirectory()
        self.j = os.path.join(self.dir.name, "recept.jsonl")
        self.t = os.path.join(self.dir.name, "temoin.jsonl")
        self.g = R.GardienReception({"F5OEG": self.KA, "OMEGA": self.KB},
                                    self.j, self.t, ScelleurHMAC(self.secret), horloge=_horloge())

    def tearDown(self):
        self.dir.cleanup()

    def test_accepte_connu_authentifie(self):
        bits = R.construire_message("F5OEG", 1, "SOS OMEGA", self.KA)
        v = self.g.recevoir_signal(afsk.moduler(bits), len(bits))
        self.assertEqual((v.decision, v.raison), (R.ACCEPTE, "authentifie"))
        self.assertEqual(v.texte, "SOS OMEGA")

    def test_authentification_invalide_mise_en_quarantaine(self):
        bad = R.construire_message("F5OEG", 2, "faux", b"Z" * 32)  # mauvaise clé
        v = self.g.recevoir(bad)
        self.assertEqual((v.decision, v.raison), (R.QUARANTAINE, "authentification_invalide"))

    def test_emetteur_inconnu_en_quarantaine_avec_raison(self):
        unk = R.construire_message("PIRATE", 3, "coucou", b"Z" * 32)
        v = self.g.recevoir(unk)
        self.assertEqual((v.decision, v.raison), (R.QUARANTAINE, "emetteur_inconnu"))

    def test_rejeu_en_quarantaine(self):
        bits = R.construire_message("F5OEG", 4, "une fois", self.KA)
        self.assertEqual(self.g.recevoir(bits).decision, R.ACCEPTE)
        rejoue = self.g.recevoir(bits)
        self.assertEqual((rejoue.decision, rejoue.raison), (R.QUARANTAINE, "rejeu"))

    def test_crc_rompu_refuse(self):
        bits = R.construire_message("F5OEG", 5, "abimé", self.KA)
        bits[40] ^= 1
        v = self.g.recevoir(bits)
        self.assertEqual((v.decision, v.raison), (R.REFUSE, "crc_invalide"))

    def test_chaque_verdict_est_scelle_et_temoigne(self):
        for cas in [R.construire_message("F5OEG", 10, "ok", self.KA),
                    R.construire_message("PIRATE", 11, "x", b"Z" * 32)]:
            self.g.recevoir(cas)
        rap = verifier_temoin(self.j, self.t, ScelleurHMAC(self.secret))
        self.assertTrue(rap.chaine.integre)
        self.assertTrue(rap.accord)
        self.assertEqual(rap.chaine.blocs, 2)

    def test_reecriture_dun_verdict_detectee(self):
        # Effacer un refus : audit local trompé, témoin en désaccord (comme rinv).
        self.g.recevoir(R.construire_message("F5OEG", 20, "bon", self.KA))
        self.g.recevoir(R.construire_message("PIRATE", 21, "pirate", b"Z" * 32))
        with open(self.j) as fh:
            blocs = [json.loads(l) for l in fh]
        blocs[1]["decision"] = "ACCEPTE"
        blocs[1]["raison"] = "authentifie"
        prev = blocs[0]["hash"]
        for b in blocs[1:]:
            b["prev_hash"] = prev
            b["hash"] = calculer_hash(b)
            prev = b["hash"]
        with open(self.j, "w") as fh:
            for b in blocs:
                fh.write(json.dumps(b, sort_keys=True, separators=(",", ":"),
                                    ensure_ascii=False) + "\n")
        self.assertTrue(verifier_chaine(self.j).integre)             # Γ seule : cohérente
        rap = verifier_temoin(self.j, self.t, ScelleurHMAC(self.secret))
        self.assertFalse(rap.accord)                                 # témoin : désaccord
        self.assertEqual(rap.raison, "desaccord_temoin")

    def test_separateur_interdit(self):
        with self.assertRaises(ValueError):
            R.construire_message("F5\x1fOEG", 1, "x", self.KA)


if __name__ == "__main__":
    unittest.main()
