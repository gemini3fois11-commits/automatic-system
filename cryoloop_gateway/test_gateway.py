import ast
import http.client
import json
import os
import stat
import tempfile
import threading
import unittest

from cryoloop_gateway import keygen
from cryoloop_gateway.gateway import DOSSIER, construire, signer_ticket
from cryoloop_gateway.ticket import fabriquer
from socle_preuve import ed25519
from socle_preuve.gamma import ChaineRompue, lire_blocs
from socle_preuve.temoin import ScelleurHMAC, verifier_temoin

MDP = "phrase de passe du proprietaire"


class Horloge:
    t = 2_000_000_000.0

    def __call__(self):
        return self.t


class Client:
    def __init__(self, port):
        self.port, self.cookie = port, None

    def __call__(self, methode, chemin, corps=None, entetes=None):
        h = {"Host": f"127.0.0.1:{self.port}", "Content-Type": "application/json", **(entetes or {})}
        if self.cookie:
            h["Cookie"] = self.cookie
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        conn.request(methode, chemin, body=None if corps is None else json.dumps(corps), headers=h)
        rep = conn.getresponse()
        donnees = rep.read()
        conn.close()
        cookie = rep.getheader("Set-Cookie")
        if cookie:
            self.cookie = cookie.split(";")[0] if "Max-Age=0" not in cookie else None
            self.dernier_cookie = cookie
        return rep.status, json.loads(donnees) if donnees else None


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.etat = os.path.join(self.tmp.name, "etat")
        self.secret = os.path.join(self.tmp.name, "t.secret")
        with open(os.open(self.secret, os.O_WRONLY | os.O_CREAT, 0o600), "wb") as fh:
            fh.write(os.urandom(32))
        self.horloge = Horloge()
        self.demarrer()

    def demarrer(self):
        self.serveur = construire(0, self.etat, horloge=self.horloge, delai_echec=0,
                                  temoin_secret=self.secret)
        threading.Thread(target=self.serveur.serve_forever, daemon=True).start()
        self.c = Client(self.serveur.server_address[1])

    def arreter(self):
        self.serveur.shutdown()
        self.serveur.server_close()

    def tearDown(self):
        self.arreter()

    def initialiser(self):
        self.graine = bytes(range(32))
        os.makedirs(self.etat, exist_ok=True)
        with open(os.path.join(self.etat, "cle_publique.hex"), "w") as fh:
            fh.write(ed25519.cle_publique(self.graine).hex())
        self.assertEqual(self.c("POST", "/api/setup", {"mot_de_passe": MDP})[0], 200)
        self.assertEqual(self.c("POST", "/api/login", {"mot_de_passe": MDP})[0], 200)

    def ticket(self, **champs):
        return fabriquer(self.graine, champs.pop("action", "inscrire"), maintenant=self.horloge.t, **champs)


class NonInitialisee(Base):
    def test_etat_public_sans_secret(self):
        code, etat = self.c("GET", "/api/etat")
        self.assertEqual((code, etat), (200, {"setup_mode": True, "cle_epinglee": False, "execute": False}))

    def test_login_refuse_en_setup_mode(self):
        self.assertEqual(self.c("POST", "/api/login", {"mot_de_passe": MDP}), (403, {"erreur": "setup_mode"}))

    def test_mot_de_passe_trop_court(self):
        self.assertEqual(self.c("POST", "/api/setup", {"mot_de_passe": "court"})[0], 400)

    def test_ticket_sans_cle_epinglee(self):
        self.c("POST", "/api/setup", {"mot_de_passe": MDP})
        self.c("POST", "/api/login", {"mot_de_passe": MDP})
        self.assertEqual(self.c("POST", "/api/ticket", {})[0], 503)

    def test_setup_une_seule_fois(self):
        self.assertEqual(self.c("POST", "/api/setup", {"mot_de_passe": MDP})[0], 200)
        self.assertEqual(self.c("POST", "/api/setup", {"mot_de_passe": "un autre mot de passe"}),
                         (409, {"erreur": "deja_configure"}))
        self.assertEqual(stat.S_IMODE(os.stat(os.path.join(self.etat, "auth.json")).st_mode), 0o600)


class Tickets(Base):
    def setUp(self):
        super().setUp()
        self.initialiser()

    def test_cookie_httponly_samesite(self):
        self.assertIn("HttpOnly", self.c.dernier_cookie)
        self.assertIn("SameSite=Strict", self.c.dernier_cookie)

    def test_ticket_valide_accepte_jamais_execute(self):
        code, r = self.c("POST", "/api/ticket", self.ticket(action="rm -rf /"))
        self.assertEqual((code, r["verdict"], r["execute"]), (200, "ACCEPTE", False))

    def test_rejeu(self):
        t = self.ticket()
        self.assertEqual(self.c("POST", "/api/ticket", t)[0], 200)
        self.assertEqual(self.c("POST", "/api/ticket", t), (403, {"refus": "ticket_rejoue"}))

    def test_rejeu_apres_redemarrage(self):
        t = self.ticket()
        self.c("POST", "/api/ticket", t)
        self.arreter()
        self.demarrer()
        self.c("POST", "/api/login", {"mot_de_passe": MDP})
        self.assertEqual(self.c("POST", "/api/ticket", t), (403, {"refus": "ticket_rejoue"}))

    def test_falsifie(self):
        t = self.ticket()
        t["ticket"]["action"] = "autre chose"
        self.assertEqual(self.c("POST", "/api/ticket", t), (403, {"refus": "signature_invalide"}))

    def test_autre_cle(self):
        t = fabriquer(bytes(range(1, 33)), "inscrire", maintenant=self.horloge.t)
        self.assertEqual(self.c("POST", "/api/ticket", t)[1], {"refus": "signature_invalide"})

    def test_expire(self):
        t = self.ticket(duree_s=60)
        self.horloge.t += 61
        self.assertEqual(self.c("POST", "/api/ticket", t), (403, {"refus": "ticket_expire"}))

    def test_pas_encore_valide(self):
        t = fabriquer(self.graine, "x", maintenant=self.horloge.t + 600)
        self.assertEqual(self.c("POST", "/api/ticket", t)[1], {"refus": "ticket_pas_encore_valide"})

    def test_fenetre_trop_longue(self):
        t = self.ticket(duree_s=7200)
        self.assertEqual(self.c("POST", "/api/ticket", t)[1], {"refus": "fenetre_invalide"})

    def test_malforme(self):
        for corps in ({}, {"ticket": {"id": "x"}, "signature": "00"}, {"ticket": [], "signature": 1}):
            self.assertEqual(self.c("POST", "/api/ticket", corps), (400, {"refus": "ticket_malforme"}))
        t = self.ticket()
        t["ticket"]["emis"] = str(t["ticket"]["emis"])
        self.assertEqual(self.c("POST", "/api/ticket", t)[0], 400)

    def test_hote_etranger(self):
        self.assertEqual(self.c("GET", "/api/etat", entetes={"Host": "evil.example"})[0], 421)

    def test_origine_etrangere(self):
        self.assertEqual(self.c("POST", "/api/ticket", self.ticket(),
                                {"Origin": "http://evil.example"}), (403, {"erreur": "origine_refusee"}))

    def test_logout(self):
        self.c("POST", "/api/logout", {})
        self.assertEqual(self.c("POST", "/api/ticket", self.ticket())[0], 401)

    def test_sans_session(self):
        self.c.cookie = None
        self.assertEqual(self.c("POST", "/api/ticket", self.ticket()), (401, {"erreur": "non_authentifie"}))
        self.assertEqual(self.c("GET", "/api/journal")[0], 401)

    def test_verrouillage(self):
        self.c.cookie = None
        for _ in range(5):
            self.assertEqual(self.c("POST", "/api/login", {"mot_de_passe": "mauvais mot de passe"})[0], 401)
        self.assertEqual(self.c("POST", "/api/login", {"mot_de_passe": MDP}), (403, {"erreur": "verrouille"}))

    def test_journal_complet_sans_mot_de_passe(self):
        self.c("POST", "/api/ticket", self.ticket())
        t = self.ticket()
        t["signature"] = "00" * 64
        self.c("POST", "/api/ticket", t)
        code, j = self.c("GET", "/api/journal")
        self.assertTrue(j["integre"])
        types = [(b["type"], b["raison"]) for b in j["derniers"]]
        self.assertEqual(types, [("auth", "setup_done"), ("auth", "login_ok"),
                                 ("ticket", "signature_valide"), ("ticket", "signature_invalide")])
        with open(os.path.join(self.etat, "passerelle.jsonl")) as fh:
            self.assertNotIn(MDP, fh.read())

    def test_temoin_detecte_une_reecriture(self):
        from socle_preuve.gamma import calculer_hash
        self.c("POST", "/api/ticket", self.ticket())
        chemin = os.path.join(self.etat, "passerelle.jsonl")
        blocs, _ = lire_blocs(chemin)
        blocs[2]["decision"] = "REFUS"
        prev = blocs[2]["prev_hash"]
        for b in blocs[2:]:
            b["prev_hash"] = prev
            b["hash"] = calculer_hash(b)
            prev = b["hash"]
        with open(chemin, "w") as fh:
            fh.writelines(json.dumps(b) + "\n" for b in blocs)
        with open(self.secret, "rb") as fh:
            r = verifier_temoin(chemin, chemin + ".temoin", ScelleurHMAC(fh.read()))
        self.assertTrue(r.chaine.integre)
        self.assertEqual((r.seq_fautif, r.raison), (2, "desaccord_temoin"))

    def test_refuse_de_demarrer_sur_un_journal_falsifie(self):
        self.arreter()
        chemin = os.path.join(self.etat, "passerelle.jsonl")
        blocs, _ = lire_blocs(chemin)
        blocs[0]["raison"] = "x"
        with open(chemin, "w") as fh:
            fh.writelines(json.dumps(b) + "\n" for b in blocs)
        with self.assertRaises(ChaineRompue):
            construire(0, self.etat)
        self.demarrer = lambda: None
        self.arreter = lambda: None


class KeygenEtArchitecture(unittest.TestCase):
    def test_keygen_hors_depot_et_sans_ecrasement(self):
        with tempfile.TemporaryDirectory() as tmp:
            cle = os.path.join(tmp, "p.cle")
            pub = keygen.generer(cle, os.path.join(tmp, "etat"))
            self.assertEqual(stat.S_IMODE(os.stat(cle).st_mode), 0o600)
            with open(cle, "rb") as fh:
                self.assertEqual(ed25519.cle_publique(fh.read()).hex(), pub)
            with self.assertRaises(FileExistsError):
                keygen.generer(cle, os.path.join(tmp, "etat"))
        with self.assertRaises(ValueError):
            keygen.generer(os.path.join(DOSSIER, "etat", "interdit.cle"), "/tmp/x")

    def test_la_passerelle_ne_peut_rien_executer(self):
        with open(os.path.join(DOSSIER, "gateway.py")) as fh:
            arbre = ast.parse(fh.read())
        imports = {a.name.split(".")[0] for n in ast.walk(arbre) if isinstance(n, ast.Import) for a in n.names}
        imports |= {(n.module or "").split(".")[0] for n in ast.walk(arbre) if isinstance(n, ast.ImportFrom)}
        self.assertFalse(imports & {"subprocess", "pty", "ctypes", "multiprocessing", "shlex"})
        appels = {n.func.attr for n in ast.walk(arbre) if isinstance(n, ast.Call)
                  and isinstance(n.func, ast.Attribute)}
        self.assertFalse(appels & {"system", "popen", "execv", "execve", "spawnv", "fork"})
        self.assertNotIn("eval", {n.func.id for n in ast.walk(arbre)
                                  if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)})


if __name__ == "__main__":
    unittest.main()
