import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest

from socle_preuve import ed25519
from socle_preuve.gamma import Chaine, calculer_hash
from socle_preuve.temoin import (ScelleurEd25519, ScelleurHMAC, Temoin, VerificateurEd25519,
                                 verifier_temoin)

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def lire(chemin):
    with open(chemin, encoding="utf-8") as fh:
        return [json.loads(l) for l in fh if l.strip()]


def ecrire(chemin, objets):
    with open(chemin, "w", encoding="utf-8") as fh:
        fh.writelines(json.dumps(o) + "\n" for o in objets)


class Base(unittest.TestCase):
    N = 8

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.j = os.path.join(self.tmp.name, "gamma.jsonl")
        self.t = os.path.join(self.tmp.name, "temoin.jsonl")
        self.hmac = ScelleurHMAC(bytes(range(32)))
        ch = Chaine(self.j, temoin=Temoin(self.t, self.scelleur()))
        for i in range(self.N):
            ch.inscrire("requete", "REFUS", "hote_non_autorise", {"i": i})

    def scelleur(self):
        return self.hmac

    def verifier(self):
        return verifier_temoin(self.j, self.t, self.scelleur())

    def reecrire(self, k):
        blocs = lire(self.j)
        blocs[k]["decision"] = "AUTORISE"
        prev = blocs[k]["prev_hash"]
        for b in blocs[k:]:
            b["prev_hash"] = prev
            b["hash"] = calculer_hash(b)
            prev = b["hash"]
        ecrire(self.j, blocs)


class TemoinHMAC(Base):
    def test_accord(self):
        r = self.verifier()
        self.assertTrue(r.accord, str(r))
        self.assertEqual(stat.S_IMODE(os.stat(self.t).st_mode), 0o600)

    def test_reecriture_detectee_bloc_par_bloc(self):
        self.reecrire(3)
        r = self.verifier()
        self.assertTrue(r.chaine.integre)  # l'audit local est trompé
        self.assertFalse(r.accord)
        self.assertEqual((r.seq_fautif, r.raison), (3, "desaccord_temoin"))
        self.assertEqual(r.seqs_en_desaccord, tuple(range(3, self.N)))

    def test_mauvais_secret(self):
        r = verifier_temoin(self.j, self.t, ScelleurHMAC(b"\x01" * 32))
        self.assertEqual((r.seq_fautif, r.raison), (0, "sceau_invalide"))

    def test_sceau_refait_par_l_attaquant(self):
        self.reecrire(5)
        recs = lire(self.t)
        faux = ScelleurHMAC(b"\x02" * 32)
        for rec, bloc in zip(recs, lire(self.j)):
            rec["hash"] = bloc["hash"]
            rec["sceau"] = faux.sceller(f"omega-gamma-temoin-v1|{rec['seq']}|{rec['hash']}".encode())
        ecrire(self.t, recs)
        r = self.verifier()
        self.assertEqual(r.raison, "sceau_invalide")
        self.assertIn(5, r.seqs_en_desaccord)

    def test_troncature_du_journal(self):
        ecrire(self.j, lire(self.j)[:5])
        r = self.verifier()
        self.assertTrue(r.chaine.integre)
        self.assertEqual((r.seq_fautif, r.raison), (5, "temoin_orphelin"))

    def test_sceau_supprime(self):
        recs = lire(self.t)
        del recs[2]
        ecrire(self.t, recs)
        self.assertEqual((self.verifier().seq_fautif, self.verifier().raison),
                         (2, "bloc_non_temoigne"))

    def test_sceau_duplique(self):
        recs = lire(self.t)
        recs.append(recs[1])
        ecrire(self.t, recs)
        self.assertEqual(self.verifier().raison, "temoin_incoherent")

    def test_ligne_temoin_illisible(self):
        with open(self.t, "a") as fh:
            fh.write("pas du json\n")
        self.assertEqual(self.verifier().raison, "temoin_illisible")

    def test_chaine_rompue_prime(self):
        blocs = lire(self.j)
        blocs[1]["raison"] = "allowlist"
        ecrire(self.j, blocs)
        r = self.verifier()
        self.assertFalse(r.chaine.integre)
        self.assertEqual((r.seq_fautif, r.raison), (1, "chaine_rompue"))

    def test_secret_trop_court(self):
        with self.assertRaises(ValueError):
            ScelleurHMAC(b"court")


class TemoinEd25519(Base):
    def scelleur(self):
        if not hasattr(self, "_ed"):
            self._ed = ScelleurEd25519(bytes(range(1, 33)))
        return self._ed

    def test_verificateur_ne_tient_que_la_cle_publique(self):
        verif = VerificateurEd25519(self.scelleur().publique)
        self.assertFalse(hasattr(verif, "sceller"))
        self.assertTrue(verifier_temoin(self.j, self.t, verif).accord)

    def test_reecriture_detectee(self):
        self.reecrire(2)
        verif = VerificateurEd25519(self.scelleur().publique)
        r = verifier_temoin(self.j, self.t, verif)
        self.assertEqual((r.seq_fautif, r.raison), (2, "desaccord_temoin"))

    def test_alg_croise_refuse(self):
        self.assertEqual(verifier_temoin(self.j, self.t, self.hmac).raison, "sceau_invalide")

    def test_autre_cle_publique(self):
        autre = VerificateurEd25519(ed25519.cle_publique(b"\x09" * 32))
        self.assertEqual(verifier_temoin(self.j, self.t, autre).raison, "sceau_invalide")


class CLI(Base):
    def cli(self, *args):
        r = subprocess.run([sys.executable, "-m", "socle_preuve", *args], cwd=RACINE,
                           capture_output=True, text=True, timeout=60)
        return r.returncode, r.stdout + r.stderr

    def secret(self, mode=0o600):
        chemin = os.path.join(self.tmp.name, "s.secret")
        if not os.path.exists(chemin):
            with open(chemin, "wb") as fh:
                fh.write(bytes(range(32)))
        os.chmod(chemin, mode)
        return chemin

    def test_codes_de_sortie_distincts(self):
        s = self.secret()
        self.assertEqual(self.cli("verifier", self.j)[0], 0)
        self.assertEqual(self.cli("verifier", self.j, "--temoin", self.t, "--secret", s)[0], 0)
        self.reecrire(4)
        code, sortie = self.cli("verifier", self.j)
        self.assertEqual(code, 0)
        code, sortie = self.cli("verifier", self.j, "--temoin", self.t, "--secret", s)
        self.assertEqual(code, 4)
        self.assertIn("seq 4", sortie)
        blocs = lire(self.j)
        blocs[6]["raison"] = "x"
        ecrire(self.j, blocs)
        code, sortie = self.cli("verifier", self.j)
        self.assertEqual(code, 3)
        self.assertIn("seq 6", sortie)

    def test_erreurs_d_usage(self):
        self.assertEqual(self.cli("verifier", "/inexistant")[0], 2)
        self.assertEqual(self.cli("verifier", self.j, "--temoin", self.t)[0], 2)
        self.assertEqual(self.cli("verifier", self.j, "--secret", self.secret())[0], 2)
        self.assertEqual(self.cli("inconnue")[0], 2)
        code, sortie = self.cli("verifier", self.j, "--temoin", self.t,
                                "--secret", self.secret(0o640))
        self.assertEqual(code, 2)
        self.assertIn("secret_permissions", sortie)

    def test_keygen(self):
        f = os.path.join(self.tmp.name, "k.secret")
        self.assertEqual(self.cli("keygen-hmac", f)[0], 0)
        self.assertEqual(stat.S_IMODE(os.stat(f).st_mode), 0o600)
        self.assertEqual(os.path.getsize(f), 32)
        self.assertEqual(self.cli("keygen-hmac", f)[0], 2)  # refus d'écraser
        cle = os.path.join(self.tmp.name, "k.cle")
        code, sortie = self.cli("keygen-ed25519", cle)
        self.assertEqual(code, 0)
        with open(cle, "rb") as fh:
            self.assertEqual(sortie.split()[-1], ed25519.cle_publique(fh.read()).hex())

    def test_le_secret_n_apparait_jamais_dans_la_sortie(self):
        s = self.secret()
        with open(s, "rb") as fh:
            valeur = fh.read().hex()
        _, sortie = self.cli("verifier", self.j, "--temoin", self.t, "--secret", s)
        self.assertNotIn(valeur, sortie)
        with open(self.t) as fh:
            self.assertNotIn(valeur, fh.read())


if __name__ == "__main__":
    unittest.main()
