import unittest

from telegraphe import trame


class CRC(unittest.TestCase):
    def test_valeur_de_controle_x25(self):
        # Valeur de contrôle normalisée de CRC-16/X-25 sur "123456789".
        self.assertEqual(trame.crc16_x25(b"123456789"), 0x906E)

    def test_crc_vide(self):
        self.assertEqual(trame.crc16_x25(b""), 0x0000)

    def test_un_bit_change_le_crc(self):
        a = trame.crc16_x25(b"OMEGA")
        b = trame.crc16_x25(b"OMEGB")
        self.assertNotEqual(a, b)


class Bourrage(unittest.TestCase):
    def test_bourrage_puis_debourrage_identite(self):
        bits = [1] * 20 + [0, 1, 0, 1] + [1] * 13
        self.assertEqual(trame._debourrer(trame._bourrer(bits)), bits)

    def test_jamais_six_uns_dans_le_contenu_bourre(self):
        bourre = trame._bourrer([1] * 40)
        uns = seen = 0
        for bit in bourre:
            uns = uns + 1 if bit == 1 else 0
            seen = max(seen, uns)
        self.assertLessEqual(seen, 5)

    def test_debourrage_refuse_six_uns(self):
        self.assertIsNone(trame._debourrer([1] * 6))


class Trame(unittest.TestCase):
    def test_aller_retour_exact(self):
        # Charge utile d'au moins un octet (une trame vide n'a pas de sens ici).
        for msg in [b"A", b"OMEGA-HERMES", bytes(range(256)), b"\x7e\x7e\x7e"]:
            bits = trame.construire(msg)
            self.assertEqual(trame.analyser(bits), msg)

    def test_charge_vide_refusee(self):
        with self.assertRaises(trame.TrameInvalide) as ctx:
            trame.analyser(trame.construire(b""))
        self.assertEqual(ctx.exception.raison, "trame_trop_courte")

    def test_fanion_dans_les_donnees_ne_casse_pas(self):
        # 0x7E en données ne doit pas être pris pour un délimiteur (bourrage).
        msg = b"\x7e\x7e\xff\xff\x7e"
        self.assertEqual(trame.analyser(trame.construire(msg)), msg)

    def test_crc_altere_rejete(self):
        msg = b"message de reference"
        bits = trame.construire(msg)
        # Retourne un bit du contenu (après 4 fanions de tête = 32 bits).
        bits[40] ^= 1
        with self.assertRaises(trame.TrameInvalide) as ctx:
            trame.analyser(bits)
        self.assertEqual(ctx.exception.raison, "crc_invalide")

    def test_aucun_fanion(self):
        with self.assertRaises(trame.TrameInvalide) as ctx:
            trame.analyser([0, 1, 0, 1, 0, 1])
        self.assertEqual(ctx.exception.raison, "aucun_fanion")


if __name__ == "__main__":
    unittest.main()
