import hashlib
import json
import os
import stat
import tempfile
import threading
import unittest

from socle_preuve.gamma import (GENESE, Chaine, ChaineRompue, calculer_hash, lire_blocs,
                                verifier_chaine)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.j = os.path.join(self.tmp.name, "gamma.jsonl")

    def remplir(self, n=6):
        ch = Chaine(self.j)
        for i in range(n):
            ch.inscrire("requete", "REFUS", "hote_non_autorise", {"i": i})
        return ch

    def lignes(self):
        with open(self.j, encoding="utf-8") as fh:
            return fh.read().splitlines()

    def ecrire_lignes(self, lignes):
        with open(self.j, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lignes) + "\n")

    def modifier(self, seq, **champs):
        lignes = self.lignes()
        bloc = json.loads(lignes[seq])
        bloc.update(champs)
        lignes[seq] = json.dumps(bloc)
        self.ecrire_lignes(lignes)


class Format(Base):
    def test_formule_du_blueprint(self):
        self.remplir(3)
        prev = GENESE
        for ligne in self.lignes():
            bloc = json.loads(ligne)
            corps = {k: v for k, v in bloc.items() if k != "hash"}
            canon = json.dumps(corps, sort_keys=True, separators=(",", ":"),
                               ensure_ascii=False).encode()
            self.assertEqual(bloc["prev_hash"], prev)
            self.assertEqual(bloc["hash"], hashlib.sha256(prev.encode() + canon).hexdigest())
            prev = bloc["hash"]

    def test_champs_et_horodatage_utc(self):
        bloc = self.remplir(1).inscrire("signal", "QUARANTAINE", "inconnu")
        for champ in ("seq", "ts", "type", "decision", "raison", "prev_hash", "hash"):
            self.assertIn(champ, bloc)
        self.assertRegex(bloc["ts"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{6}Z$")
        self.assertEqual(bloc["seq"], 1)

    def test_mode_600_meme_si_le_fichier_existait_ouvert(self):
        open(self.j, "w").close()
        os.chmod(self.j, 0o644)
        self.remplir(1)
        self.assertEqual(stat.S_IMODE(os.stat(self.j).st_mode), 0o600)

    def test_unicode_et_donnees(self):
        self.remplir(0)
        Chaine(self.j).inscrire("requete", "REFUS", "exfiltration_hote", {"hôte": "é.example"})
        self.assertTrue(verifier_chaine(self.j).integre)

    def test_champs_vides_refuses(self):
        ch = self.remplir(0)
        with self.assertRaises(ValueError):
            ch.inscrire("requete", "", "x")

    def test_journal_vide_est_integre(self):
        self.remplir(0)
        r = verifier_chaine(self.j)
        self.assertTrue(r.integre)
        self.assertEqual((r.blocs, r.tete), (0, GENESE))

    def test_reprise_apres_reouverture(self):
        self.remplir(3)
        bloc = Chaine(self.j).inscrire("requete", "AUTORISE", "allowlist")
        self.assertEqual(bloc["seq"], 3)
        self.assertEqual(verifier_chaine(self.j).blocs, 4)


class Falsifications(Base):
    def assertRompue(self, seq, raison):
        r = verifier_chaine(self.j)
        self.assertFalse(r.integre)
        self.assertEqual((r.seq_fautif, r.raison), (seq, raison))

    def test_champ_modifie(self):
        self.remplir()
        self.modifier(3, raison="allowlist")
        self.assertRompue(3, "hash_invalide")

    def test_bloc_supprime(self):
        self.remplir()
        lignes = self.lignes()
        del lignes[2]
        self.ecrire_lignes(lignes)
        self.assertRompue(2, "seq_inattendu")

    def test_blocs_permutes(self):
        self.remplir()
        lignes = self.lignes()
        lignes[1], lignes[2] = lignes[2], lignes[1]
        self.ecrire_lignes(lignes)
        self.assertRompue(1, "seq_inattendu")

    def test_prev_hash_rompu(self):
        self.remplir()
        lignes = self.lignes()
        bloc = json.loads(lignes[4])
        bloc["prev_hash"] = "f" * 64
        bloc["hash"] = calculer_hash(bloc)
        lignes[4] = json.dumps(bloc)
        self.ecrire_lignes(lignes)
        self.assertRompue(4, "prev_hash_rompu")

    def test_ligne_tronquee(self):
        self.remplir()
        with open(self.j, "rb+") as fh:
            fh.truncate(os.path.getsize(self.j) - 20)
        self.assertRompue(5, "json_invalide")

    def test_champ_manquant(self):
        self.remplir()
        lignes = self.lignes()
        bloc = json.loads(lignes[0])
        del bloc["raison"]
        lignes[0] = json.dumps(bloc)
        self.ecrire_lignes(lignes)
        self.assertRompue(0, "champ_manquant")

    def test_seq_booleen_refuse(self):
        self.remplir(1)
        lignes = self.lignes()
        bloc = json.loads(lignes[0])
        bloc["seq"] = False
        bloc["hash"] = calculer_hash(bloc)
        lignes[0] = json.dumps(bloc)
        self.ecrire_lignes(lignes)
        self.assertRompue(0, "seq_inattendu")

    def test_refus_d_ecrire_sur_une_chaine_rompue(self):
        self.remplir()
        self.modifier(1, decision="AUTORISE")
        with self.assertRaises(ChaineRompue) as ctx:
            Chaine(self.j)
        self.assertEqual(ctx.exception.rapport.seq_fautif, 1)

    def test_reecriture_avec_recalcul_passe_l_audit_local(self):
        """[DÉMONTRÉ] §3.1 : c'est pour ça que le témoin existe."""
        self.remplir()
        blocs, _ = lire_blocs(self.j)
        blocs[2]["decision"] = "AUTORISE"
        prev = blocs[2]["prev_hash"]
        for b in blocs[2:]:
            b["prev_hash"] = prev
            b["hash"] = calculer_hash(b)
            prev = b["hash"]
        self.ecrire_lignes([json.dumps(b) for b in blocs])
        self.assertTrue(verifier_chaine(self.j).integre)


class Concurrence(Base):
    def test_deux_ecrivains_deux_threads(self):
        self.remplir(0)
        a, b = Chaine(self.j), Chaine(self.j)

        def ecrire(ch):
            for _ in range(40):
                ch.inscrire("requete", "REFUS", "hote_non_autorise")

        threads = [threading.Thread(target=ecrire, args=(c,)) for c in (a, b)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        r = verifier_chaine(self.j)
        self.assertTrue(r.integre, str(r))
        self.assertEqual(r.blocs, 80)


if __name__ == "__main__":
    unittest.main()
