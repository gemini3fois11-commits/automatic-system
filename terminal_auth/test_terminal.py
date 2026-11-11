import http.client
import json
import os
import re
import tempfile
import threading
import unittest
from unittest import mock

from socle_preuve.gamma import lire_blocs
from terminal_auth import server
from terminal_auth.server import DOSSIER, construire

MDP = "phrase de passe du terminal"


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.etat = os.path.join(self.tmp.name, "etat")
        self.s = construire(0, self.etat, delai_echec=0)
        threading.Thread(target=self.s.serve_forever, daemon=True).start()
        self.addCleanup(self.s.server_close)
        self.addCleanup(self.s.shutdown)
        self.port = self.s.server_address[1]
        self.cookie = None

    def req(self, methode, chemin, corps=None, entetes=None):
        h = {"Host": f"127.0.0.1:{self.port}", **(entetes or {})}
        if self.cookie:
            h["Cookie"] = self.cookie
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=15)
        conn.request(methode, chemin, body=None if corps is None else json.dumps(corps), headers=h)
        r = conn.getresponse()
        brut = r.read()
        conn.close()
        if r.getheader("Set-Cookie"):
            c = r.getheader("Set-Cookie")
            self.cookie = None if "Max-Age=0" in c else c.split(";")[0]
        donnees = json.loads(brut) if r.getheader("Content-Type", "").startswith("application/json") else brut
        return r.status, donnees, r

    def ouvrir(self):
        self.req("POST", "/api/setup", {"mot_de_passe": MDP})
        self.assertEqual(self.req("POST", "/api/login", {"mot_de_passe": MDP})[0], 200)

    def execs(self):
        return [b for b in lire_blocs(os.path.join(self.etat, "audit.jsonl"))[0] if b["type"] == "exec"]


class SansSession(Base):
    def test_setup_mode_par_defaut(self):
        self.assertEqual(self.req("GET", "/api/etat")[1], {"setup_mode": True, "session": False})

    def test_exec_sans_session_401_et_rien_execute(self):
        self.req("POST", "/api/setup", {"mot_de_passe": MDP})
        self.assertEqual(self.req("POST", "/api/exec", {"commande": "echo x"})[0], 401)
        self.assertEqual(self.req("GET", "/api/exec?cmd=echo%20x")[0], 401)
        self.assertEqual(self.execs(), [])

    def test_page_sans_script_en_ligne_et_avec_csp(self):
        code, page, r = self.req("GET", "/")
        self.assertEqual(code, 200)
        self.assertIn("default-src 'self'", r.getheader("Content-Security-Policy"))
        self.assertIsNone(re.search(rb"<script>[^<]", page))
        self.assertNotIn(b"http://", page.replace(b"http://www.w3.org", b""))
        self.assertNotIn(b"https://", page)

    def test_audit_exige_une_session(self):
        self.assertEqual(self.req("GET", "/api/audit")[0], 401)


class AvecSession(Base):
    def setUp(self):
        super().setUp()
        self.ouvrir()

    def run_(self, commande):
        return self.req("POST", "/api/exec", {"commande": commande})

    def test_echo(self):
        code, d, _ = self.run_("echo bonjour le monde")
        self.assertEqual((code, d["sortie"], d["code_retour"]), (200, "bonjour le monde\n", 0))

    def test_bac_a_sable(self):
        self.assertEqual(self.run_("pwd")[1]["sortie"].strip(), os.path.join(self.etat, "sandbox"))

    def test_get_avec_session_n_execute_toujours_pas(self):
        n = len(self.execs())
        self.assertEqual(self.req("GET", "/api/exec?commande=echo")[0], 405)
        self.assertEqual(len(self.execs()), n)

    def test_commandes_refusees(self):
        for c in ("rm -rf /", "bash", "python3 -c 1", "sh -c id", "/bin/echo x", "cat /etc/passwd", ""):
            code, d, _ = self.run_(c)
            self.assertEqual(code, 403, c)

    def test_politique_d_arguments(self):
        for c, raison in (("ls /", "arguments_non_autorises"), ("ls ../..", "arguments_non_autorises"),
                          ("ls a/../../b", "arguments_non_autorises"), ("uname -X", "arguments_non_autorises"),
                          ("pwd -P", "arguments_non_autorises"), ("date -s 2000-01-01", "arguments_non_autorises")):
            self.assertEqual(self.run_(c)[1], {"refus": raison}, c)
        self.assertEqual(self.run_("ls -la")[0], 200)
        self.assertEqual(self.run_("date +%Y")[0], 200)

    def test_pas_d_interpretation_shell(self):
        d = self.run_("echo $(id) ; `whoami` | cat > x")[1]
        self.assertEqual(d["sortie"], "$(id) ; `whoami` | cat > x\n")
        self.assertEqual(os.listdir(os.path.join(self.etat, "sandbox")), [])

    def test_internes(self):
        self.assertIn("omega-statut", self.run_("help")[1]["sortie"])
        self.assertIn("INTÈGRE", self.run_("omega-statut")[1]["sortie"])

    def test_plafond_de_sortie_memoire_bornee(self):
        with mock.patch.dict(server.POLITIQUE, {"yes": lambda a: True}):
            code, d, _ = self.run_("yes")                 # sortie infinie
        self.assertEqual(code, 200)
        self.assertNotEqual(d["code_retour"], 0)          # tué dès le plafond atteint
        self.assertIn("[sortie_tronquee]", d["sortie"])
        self.assertLessEqual(len(d["sortie"].encode()), 64 * 1024 + 100)

    def test_delai_de_5_s(self):
        with mock.patch.dict(server.POLITIQUE, {"sleep": lambda a: True}):
            code, d, _ = self.run_("sleep 30")
        self.assertEqual(d["code_retour"], 124)
        self.assertIn("[delai_depasse]", d["sortie"])

    def test_journal_d_audit(self):
        self.run_("echo a")
        self.run_("rm x")
        self.req("POST", "/api/logout", {})
        self.req("POST", "/api/login", {"mot_de_passe": "mauvais mot de passe"})
        blocs = lire_blocs(os.path.join(self.etat, "audit.jsonl"))[0]
        self.assertEqual([b["raison"] for b in blocs],
                         ["setup_done", "login_ok", "allowlist", "commande_non_autorisee", "logout", "login_fail"])
        with open(os.path.join(self.etat, "audit.jsonl")) as fh:
            self.assertNotIn(MDP, fh.read())

    def test_verrouillage(self):
        self.cookie = None
        for _ in range(5):
            self.req("POST", "/api/login", {"mot_de_passe": "mauvais mot de passe"})
        self.assertEqual(self.req("POST", "/api/login", {"mot_de_passe": MDP})[1], {"erreur": "verrouille"})
        self.assertIn("locked", [b["raison"] for b in lire_blocs(os.path.join(self.etat, "audit.jsonl"))[0]])


if __name__ == "__main__":
    unittest.main()
