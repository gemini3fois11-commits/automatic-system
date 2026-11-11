import json
import os
import stat
import tempfile
import unittest

from socle_preuve.auth import (ECHECS_MAX, SESSION_S, VERROU_S, Authentificateur, ErreurAuth)
from socle_preuve.porte_http import Serveur

MDP = "correct horse battery"


class Horloge:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


class Auth(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.h = Horloge()
        self.evts = []
        self.a = Authentificateur(os.path.join(self.tmp.name, "auth.json"), horloge=self.h,
                                  delai_echec=0, evenement=lambda t, d: self.evts.append(t))

    def code(self, f, *args):
        with self.assertRaises(ErreurAuth) as ctx:
            f(*args)
        return ctx.exception.code

    def test_setup_mode_puis_configuration_unique(self):
        self.assertTrue(self.a.setup_mode)
        self.assertEqual(self.code(self.a.connecter, MDP), "setup_mode")
        self.assertEqual(self.code(self.a.configurer, "court"), "mot_de_passe_trop_court")
        self.a.configurer(MDP)
        self.assertFalse(self.a.setup_mode)
        self.assertEqual(stat.S_IMODE(os.stat(self.a.fichier).st_mode), 0o600)
        self.assertEqual(self.code(self.a.configurer, "autre mot de passe"), "deja_configure")

    def test_le_mot_de_passe_n_est_jamais_stocke(self):
        self.a.configurer(MDP)
        with open(self.a.fichier) as fh:
            contenu = fh.read()
        self.assertNotIn(MDP, contenu)
        self.assertEqual(json.loads(contenu)["alg"], "scrypt")

    def test_session_glissante(self):
        self.a.configurer(MDP)
        jeton = self.a.connecter(MDP)
        self.assertEqual(len(jeton), 64)                    # 256 bits
        self.h.t += SESSION_S - 1
        self.assertTrue(self.a.valider(jeton))              # prolonge
        self.h.t += SESSION_S - 1
        self.assertTrue(self.a.valider(jeton))
        self.h.t += SESSION_S
        self.assertFalse(self.a.valider(jeton))
        self.assertFalse(self.a.valider("0" * 64))
        self.assertFalse(self.a.valider(None))

    def test_deconnexion(self):
        self.a.configurer(MDP)
        jeton = self.a.connecter(MDP)
        self.a.deconnecter(jeton)
        self.assertFalse(self.a.valider(jeton))

    def test_verrouillage_apres_5_echecs(self):
        self.a.configurer(MDP)
        for _ in range(ECHECS_MAX):
            self.assertEqual(self.code(self.a.connecter, "mauvais mot de passe"),
                             "identifiants_invalides")
        self.assertEqual(self.code(self.a.connecter, MDP), "verrouille")  # même le bon
        self.h.t += VERROU_S
        self.assertTrue(self.a.valider(self.a.connecter(MDP)))
        self.assertIn("locked", self.evts)

    def test_echecs_anciens_oublies(self):
        self.a.configurer(MDP)
        for _ in range(ECHECS_MAX - 1):
            self.code(self.a.connecter, "mauvais mot de passe")
        self.h.t += 601
        self.code(self.a.connecter, "mauvais mot de passe")
        self.assertTrue(self.a.valider(self.a.connecter(MDP)))

    def test_evenements_sans_secret(self):
        self.a.configurer(MDP)
        self.code(self.a.connecter, "x" * 12)
        self.a.deconnecter(self.a.connecter(MDP))
        self.assertEqual(self.evts, ["setup_done", "login_fail", "login_ok", "logout"])


class Liaison(unittest.TestCase):
    def test_refuse_toute_autre_interface(self):
        with self.assertRaises(ValueError):
            Serveur(0, None, hote="0.0.0.0")


if __name__ == "__main__":
    unittest.main()
