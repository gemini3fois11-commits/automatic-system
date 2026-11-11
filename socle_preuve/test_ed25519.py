import os
import random
import unittest

from socle_preuve import ed25519
from socle_preuve.vecteurs_rfc8032 import VECTEURS, verifier_vecteurs

try:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
except ImportError:  # dépendance de contrôle croisé uniquement, jamais requise
    Ed25519PrivateKey = None


class VecteursRFC8032(unittest.TestCase):
    def test_tous_les_controles(self):
        for nom, controle, ok in verifier_vecteurs():
            with self.subTest(vecteur=nom, controle=controle):
                self.assertTrue(ok)


class Refus(unittest.TestCase):
    def setUp(self):
        _, sk, pk, msg, sig = VECTEURS[2]
        self.pk, self.msg, self.sig = bytes.fromhex(pk), bytes.fromhex(msg), bytes.fromhex(sig)

    def test_message_altere(self):
        self.assertFalse(ed25519.verifier(self.pk, self.msg + b"\0", self.sig))

    def test_chaque_bit_de_signature(self):
        for i in range(0, 512, 7):
            sig = bytearray(self.sig)
            sig[i // 8] ^= 1 << (i % 8)
            self.assertFalse(ed25519.verifier(self.pk, self.msg, bytes(sig)), i)

    def test_mauvaise_cle(self):
        autre = bytes.fromhex(VECTEURS[0][2])
        self.assertFalse(ed25519.verifier(autre, self.msg, self.sig))

    def test_malleabilite_s_plus_l(self):
        s = int.from_bytes(self.sig[32:], "little") + ed25519.L
        self.assertLess(s, 2**256)
        sig = self.sig[:32] + s.to_bytes(32, "little")
        self.assertFalse(ed25519.verifier(self.pk, self.msg, sig))

    def test_longueurs(self):
        self.assertFalse(ed25519.verifier(self.pk[:31], self.msg, self.sig))
        self.assertFalse(ed25519.verifier(self.pk, self.msg, self.sig[:63]))
        with self.assertRaises(ValueError):
            ed25519.signer(b"court", b"")

    def test_cle_publique_hors_courbe(self):
        y_trop_grand = (ed25519.p).to_bytes(32, "little")
        self.assertFalse(ed25519.verifier(y_trop_grand, self.msg, self.sig))
        # y = 2 ne donne aucun x : (y²−1)/(d·y²+1) n'est pas un carré
        self.assertIsNone(ed25519._decoder((2).to_bytes(32, "little")))


@unittest.skipIf(Ed25519PrivateKey is None, "bibliothèque cryptography absente")
class ControleCroise(unittest.TestCase):
    def test_cles_et_messages_aleatoires(self):
        rng = random.Random(7)
        for _ in range(25):
            graine = rng.randbytes(32)
            msg = rng.randbytes(rng.randrange(0, 300))
            ref = Ed25519PrivateKey.from_private_bytes(graine)
            pub = ref.public_key().public_bytes(serialization.Encoding.Raw,
                                                serialization.PublicFormat.Raw)
            self.assertEqual(ed25519.cle_publique(graine), pub)
            self.assertEqual(ed25519.signer(graine, msg), ref.sign(msg))
            self.assertTrue(ed25519.verifier(pub, msg, ref.sign(msg)))


if __name__ == "__main__":
    unittest.main()
