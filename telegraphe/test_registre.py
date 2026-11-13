import itertools
import json
import os
import tempfile
import unittest

from socle_preuve.gamma import calculer_hash, verifier_chaine
from socle_preuve.temoin import ScelleurHMAC
from telegraphe import registre


def _horloge():
    c = itertools.count()
    return lambda: f"2026-01-01T00:00:{next(c):02d}.000000Z"


class RegistreScelle(unittest.TestCase):
    def setUp(self):
        self.secret = b"s" * 32
        self.dir = tempfile.TemporaryDirectory()
        self.j = os.path.join(self.dir.name, "emissions.jsonl")
        self.t = os.path.join(self.dir.name, "temoin.jsonl")

    def tearDown(self):
        self.dir.cleanup()

    def _registre(self):
        return registre.Registre(self.j, self.t, ScelleurHMAC(self.secret), horloge=_horloge())

    def test_emission_scellee_et_signal_valide(self):
        from telegraphe import afsk, trame
        reg = self._registre()
        r = reg.emettre("OMEGA HERMES")
        # Le bloc porte les mesures du message, pas le son.
        self.assertEqual(r["donnees"]["texte"], "OMEGA HERMES")
        self.assertNotIn("signal", r["bloc"].get("donnees", {}))
        # Le signal scellé se démodule bien vers le message d'origine.
        recu = trame.analyser(afsk.demoduler(r["signal"], len(r["bits"])))
        self.assertEqual(recu.decode("utf-8"), "OMEGA HERMES")

    def test_temoin_en_accord_sur_chaine_saine(self):
        reg = self._registre()
        for m in ["SOS", "OMEGA HERMES", "GRAINE 7."]:
            reg.emettre(m)
        rap = registre.verifier(self.j, self.t, ScelleurHMAC(self.secret))
        self.assertTrue(rap.chaine.integre)
        self.assertTrue(rap.accord)
        self.assertEqual(rap.chaine.blocs, 3)

    def test_reecriture_avec_recalcul_detectee_par_le_temoin(self):
        reg = self._registre()
        for m in ["SOS", "OMEGA HERMES", "GRAINE 7."]:
            reg.emettre(m)

        with open(self.j) as fh:
            lignes = fh.readlines()
        # Falsifie le bloc 1 et recalcule toute la suite : la chaîne Γ seule
        # redevient cohérente. Seul le témoin doit encore refuser.
        blocs = [json.loads(l) for l in lignes]
        blocs[1]["donnees"]["texte"] = "FALSIFIE"
        prev = blocs[0]["hash"]
        for b in blocs[1:]:
            b["prev_hash"] = prev
            b["hash"] = calculer_hash(b)
            prev = b["hash"]
        with open(self.j, "w") as fh:
            for b in blocs:
                fh.write(json.dumps(b, sort_keys=True, separators=(",", ":"),
                                    ensure_ascii=False) + "\n")

        self.assertTrue(verifier_chaine(self.j).integre)  # Γ seule : cohérente
        rap = registre.verifier(self.j, self.t, ScelleurHMAC(self.secret))
        self.assertFalse(rap.accord)                      # témoin : désaccord
        self.assertEqual(rap.seq_fautif, 1)
        self.assertEqual(rap.raison, "desaccord_temoin")

    def test_mauvais_secret_ne_verifie_pas(self):
        reg = self._registre()
        reg.emettre("SOS")
        rap = registre.verifier(self.j, self.t, ScelleurHMAC(b"a" * 32))
        self.assertFalse(rap.accord)


if __name__ == "__main__":
    unittest.main()
