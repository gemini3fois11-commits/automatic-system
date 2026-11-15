import os
import shutil
import tempfile
import unittest

from rag_wiki import pinning
from rag_wiki.corpus import charger, nettoyer
from rag_wiki.fusion import Fusion, repondre
from rag_wiki.rag import IndexTFIDF, decouper, jetons, mrr, repondre_avec


def _der_len(n: int) -> bytes:
    if n < 0x80:
        return bytes([n])
    corps = n.to_bytes((n.bit_length() + 7) // 8, "big")
    return bytes([0x80 | len(corps)]) + corps


def _tlv(tag: int, contenu: bytes) -> bytes:
    return bytes([tag]) + _der_len(len(contenu)) + contenu


def _seq(*enfants: bytes) -> bytes:
    return _tlv(0x30, b"".join(enfants))


def _cert(champs: list[bytes]) -> bytes:
    """Certificat DER synthétique : SEQUENCE { TBSCertificate(champs) }.

    analyser() ne lit que le premier enfant (le TBS) ; inutile de forger
    l'algorithme de signature ni la signature.
    """
    return _seq(_seq(*champs))


class Corpus(unittest.TestCase):
    def test_tracable(self):
        c = charger()
        self.assertEqual(len(c["documents"]), 12)
        self.assertIn("CC BY-SA", c["licence"])
        for d in c["documents"]:
            self.assertTrue(d["url"].startswith("https://fr.wikipedia.org/wiki/"))
            self.assertIsInstance(d["revision"], int)
            self.assertNotRegex(d["texte"], r"(?m)^==")

    def test_chiffres_et_dates_conserves(self):
        from rag_wiki.rag import annees_par_document
        annees = annees_par_document(charger())
        self.assertGreaterEqual(min(annees.values()), 3, annees)
        morse = next(d for d in charger()["documents"] if d["titre"] == "Télégraphie électrique")
        self.assertIn("1838", morse["texte"])

    def test_methode_de_collecte_tracee(self):
        self.assertIn("Action API", charger()["methode"])

    def test_latex_retire(self):
        from rag_wiki.corpus import sans_latex
        self.assertEqual(sans_latex("a {\\displaystyle x_{k}^{2}} b"), "a  b")

    def test_titres_de_section_reduits(self):
        self.assertEqual(nettoyer("== Histoire ==\ntexte"), "Histoire.\ntexte")


class RAG(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.morceaux = decouper(charger())
        cls.index = IndexTFIDF(cls.morceaux)

    def test_decoupage_avec_chevauchement(self):
        a, b = self.morceaux[0]["texte"], self.morceaux[1]["texte"]
        self.assertLessEqual(len(a), 500)
        self.assertEqual(a[-100:], b[:100])

    def test_aucun_morceau_vide(self):
        self.assertTrue(all(len(jetons(m["texte"])) >= 20 for m in self.morceaux))

    def test_jetons_sans_accents_ni_mots_vides(self):
        self.assertEqual(jetons("Qu'est-ce que l'Étoile ?"), ["etoile"])

    def test_mrr_tfidf(self):
        self.assertGreaterEqual(mrr(self.index.classer, self.morceaux)["mrr"], 0.75)

    def test_reponse_citee_ou_aveu(self):
        r = repondre_avec(self.index.classer, self.morceaux, "Quel est le satellite naturel de la Terre ?")
        self.assertTrue(r["citations"])
        for c in r["citations"]:
            self.assertIn(c["extrait"], next(m["texte"] for m in self.morceaux
                                             if m["titre"] == c["titre"] and c["extrait"] in m["texte"]))
        self.assertIsNone(repondre_avec(self.index.classer, self.morceaux, "xqzw vbnk")["reponse"])

    def test_fusion_trois_voies_sans_hf(self):
        f = Fusion(self.morceaux)
        self.assertEqual(set(f.strategies), {"tfidf", "bm25", "entites"})
        self.assertFalse(f.hf_actif)
        self.assertTrue(repondre("filtre de Kalman")["citations"])


class Epinglage(unittest.TestCase):
    def lire(self, n):
        with open(os.path.join(pinning.CERTS, n), "rb") as fh:
            return fh.read()

    def test_chaine_fichiers(self):
        ep = set(pinning.charger_epingles().values())
        chaine = [self.lire("int-ye2.der"), self.lire("root-ye-by-x2.der"), self.lire("isrg-root-x2.der")]
        self.assertEqual(pinning.verifier_chaine(chaine, ep)[0], "PINNED_OK")
        self.assertEqual(pinning.verifier_chaine(chaine, set())[0], "PINNED_FAIL")

    def test_der_invalide(self):
        for mauvais in (b"", b"\x30", b"\x30\x84\xff\xff\xff\xff", b"\x02\x01\x00"):
            with self.assertRaises(pinning.DERInvalide):
                pinning.analyser(mauvais)

    def test_longueur_longue_invalide_refusee(self):
        # Forme longue mal encodée : 0 octet de longueur, > 4 octets, longueur au-delà de la fin.
        for mauvais in (b"\x30\x80", b"\x30\x85\x01\x02\x03\x04\x05", b"\x30\x84\xff"):
            with self.assertRaises(pinning.DERInvalide):
                pinning.analyser(mauvais)

    def test_tbs_sans_version_six_champs_accepte(self):
        # Pas de [0] version : le parseur ne saute rien et lit directement les six champs.
        i, s, spki = _seq(b"\x01"), _seq(b"\x02"), _seq(b"\x03")
        champs = [_tlv(0x02, b"\x00"), _tlv(0x02, b"\x00"), i, _seq(), s, spki]
        r = pinning.analyser(_cert(champs))
        self.assertEqual((r["issuer"], r["subject"], r["spki"]), (i, s, spki))

    def test_tbs_incomplet_refuse(self):
        # Cinq champs, pas de version : TBSCertificate incomplet.
        with self.assertRaises(pinning.DERInvalide):
            pinning.analyser(_cert([_tlv(0x02, b"\x00")] * 5))

    def test_chaine_non_liee_refusee(self):
        def cert(issuer, subject):
            return _cert([_tlv(0x02, b"\x00"), _tlv(0x02, b"\x00"), issuer, _seq(), subject, _seq(b"\x09")])
        a = cert(_seq(b"\xAA"), _seq(b"\x01"))
        b = cert(_seq(b"\xBB"), _seq(b"\x02"))      # subject de b ≠ issuer de a
        self.assertEqual(pinning.verifier_chaine([a, b], set()), ("PINNED_FAIL", "chaine_non_liee"))

    @unittest.skipUnless(shutil.which("openssl"), "openssl requis")
    def test_interception_rejetee(self):
        # Une feuille letsencrypt.org ré-émise par une autorité étrangère : la chaîne est liée
        # par les noms mais ne porte aucune clé épinglée → refusée. C'est la propriété centrale.
        ep = set(pinning.charger_epingles().values())
        with tempfile.TemporaryDirectory() as tmp:
            forgee = pinning.chaine_interception(tmp)
        self.assertEqual(pinning.verifier_chaine(forgee, ep), ("PINNED_FAIL", "aucune_epingle"))


if __name__ == "__main__":
    unittest.main()
