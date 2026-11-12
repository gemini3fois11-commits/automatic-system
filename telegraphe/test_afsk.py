import unittest

from telegraphe.afsk import (ECH_PAR_BIT, FE, ErreurTrame, bits_trame, bruiter_bits, crc16_x25,
                             demoduler, depuis_wav, moduler, vers_wav)

MESSAGE = "CQ CQ DE OMEGA — refuser avant de croire".encode()


class Modem(unittest.TestCase):
    def test_crc_valeur_de_controle(self):
        self.assertEqual(crc16_x25(b"123456789"), 0x906E)

    def test_aller_retour_exact(self):
        self.assertEqual(demoduler(moduler(MESSAGE)), MESSAGE)

    def test_bourrage_de_bits(self):
        for charge in (b"\xff" * 20, b"\x7e\x7e\x7e", b"\x00" * 8, bytes(range(256))):
            self.assertEqual(demoduler(moduler(charge)), charge)
            bits = bits_trame(charge)[32:-16]
            self.assertNotIn("111111", "".join(map(str, bits)))     # jamais six 1 dans les données

    def test_376_bits_donnent_6909_echantillons(self):
        """Le chiffre du blueprint (6 909 échantillons, 313 ms) correspond à une trame de 376 bits."""
        self.assertEqual(int(376 * ECH_PAR_BIT + 0.5), 6909)
        self.assertAlmostEqual(6909 / FE, 0.313, places=3)

    def test_silence_avant_et_apres(self):
        for avance in (0, 1, 7, 13, 100, 2205):
            x = [0.0] * avance + moduler(MESSAGE) + [0.0] * 50
            self.assertEqual(demoduler(x), MESSAGE, avance)

    def test_trame_alteree_rejetee(self):
        """Du bruit blanc dans la zone des données doit toujours faire tomber le CRC."""
        n_bits = len(bits_trame(MESSAGE))
        # 40 = juste après le préambule (32 bits de fanions). On corrompt 8 bits = 1 octet
        # de signal, nettement plus que le CRC ne peut masquer.
        for premier in range(40, n_bits - 24, 37):
            x = moduler(MESSAGE)
            bruiter_bits(x, premier, 8, graine=premier)
            with self.assertRaises(ErreurTrame, msg=premier) as ctx:
                demoduler(x)
            self.assertIn(ctx.exception.code, ("crc_invalide", "aucune_trame"))

    def test_inversion_de_signe_sans_effet(self):
        """Goertzel mesure une puissance : inverser la polarité du câble ne change rien."""
        self.assertEqual(demoduler([-v for v in moduler(MESSAGE)]), MESSAGE)

    def test_silence_seul(self):
        with self.assertRaises(ErreurTrame) as ctx:
            demoduler([0.0] * 5000)
        self.assertEqual(ctx.exception.code, "aucune_trame")

    def test_wav_aller_retour(self):
        wav = vers_wav(moduler(MESSAGE))
        self.assertEqual(wav[:4], b"RIFF")
        self.assertEqual(demoduler(depuis_wav(wav)), MESSAGE)
        with self.assertRaises(ErreurTrame):
            depuis_wav(b"pas un wav" * 10)


if __name__ == "__main__":
    unittest.main()
