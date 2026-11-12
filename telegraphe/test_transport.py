import os
import tempfile
import unittest

from socle_preuve.gamma import Chaine, calculer_hash, lire_blocs
from socle_preuve.temoin import ScelleurHMAC, Temoin, verifier_temoin
from telegraphe.afsk import bruiter_bits
from telegraphe.transport import Recepteur, emettre, envelopper


class EnveloppeEtTransport(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.secret = os.path.join(self.tmp.name, "temoin.secret")
        with open(os.open(self.secret, os.O_WRONLY | os.O_CREAT, 0o600), "wb") as fh:
            fh.write(os.urandom(32))
        with open(self.secret, "rb") as fh:
            self.scelleur = ScelleurHMAC(fh.read())
        self.chemin = os.path.join(self.tmp.name, "telegraphe.jsonl")
        self.temoin = os.path.join(self.tmp.name, "telegraphe.temoin.jsonl")
        self.journal = Chaine(self.chemin, temoin=Temoin(self.temoin, self.scelleur))
        self.r = Recepteur(self.journal)

    def test_enveloppe_refuse_les_textes_hors_contraintes(self):
        for mauvais in ("", "x" * 1000, 42, None):
            with self.assertRaises(ValueError):
                envelopper(1, mauvais)
        for mauvais in (-1, 1.5, "a"):
            with self.assertRaises(ValueError):
                envelopper(mauvais, "ok")

    def test_trame_valide_scellee_et_temoignee(self):
        r = self.r.recevoir(emettre(1, "CQ CQ DE OMEGA"))
        self.assertTrue(r["accepte"])
        rap = verifier_temoin(self.chemin, self.temoin, self.scelleur)
        self.assertTrue(rap.accord, str(rap))

    def test_crc_invalide_refuse(self):
        x = emettre(1, "message intègre")
        bruiter_bits(x, 50, 8, graine=50)
        r = self.r.recevoir(x)
        self.assertEqual(r, {"accepte": False, "code": "crc_invalide"})

    def test_seq_non_croissant(self):
        self.r.recevoir(emettre(5, "premier"))
        self.assertEqual(self.r.recevoir(emettre(5, "rejeu"))["code"], "seq_non_croissant")
        self.assertEqual(self.r.recevoir(emettre(3, "avant"))["code"], "seq_non_croissant")
        self.assertTrue(self.r.recevoir(emettre(6, "suite"))["accepte"])

    def test_enveloppe_malformee(self):
        # Trame JSON non-conforme mais CRC valide
        import json
        from telegraphe.afsk import moduler
        r = self.r.recevoir(moduler(json.dumps({"seq": 1}).encode()))
        self.assertEqual(r["code"], "enveloppe_malformee")
        r2 = self.r.recevoir(moduler(b"pas du json"))
        self.assertEqual(r2["code"], "enveloppe_malformee")

    def test_reprise_depuis_journal(self):
        self.r.recevoir(emettre(7, "a"))
        self.r.recevoir(emettre(8, "b"))
        r2 = Recepteur(Chaine(self.chemin, temoin=Temoin(self.temoin, self.scelleur)))
        self.assertEqual(r2._dernier_seq, 8)
        self.assertEqual(r2.recevoir(emettre(8, "rejeu"))["code"], "seq_non_croissant")
        self.assertTrue(r2.recevoir(emettre(9, "suite"))["accepte"])

    def test_reecriture_apres_scellement_detectee_par_temoin(self):
        for i in (1, 2, 3):
            self.r.recevoir(emettre(i, f"m{i}"))
        # L'attaquant réécrit le texte du bloc seq=2 et recalcule la chaîne
        import json
        blocs, _ = lire_blocs(self.chemin)
        cible = next(i for i, b in enumerate(blocs) if b["type"] == "telegraphe" and b["donnees"].get("seq") == 2)
        blocs[cible]["donnees"]["texte"] = "falsifié"
        prev = blocs[cible]["prev_hash"]
        for b in blocs[cible:]:
            b["prev_hash"] = prev
            b["hash"] = calculer_hash(b)
            prev = b["hash"]
        with open(self.chemin, "w") as fh:
            fh.writelines(json.dumps(b, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n" for b in blocs)
        rap = verifier_temoin(self.chemin, self.temoin, self.scelleur)
        self.assertFalse(rap.accord)
        self.assertEqual((rap.seq_fautif, rap.raison), (cible, "desaccord_temoin"))


if __name__ == "__main__":
    unittest.main()
