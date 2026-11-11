import json
import os
import tempfile
import unittest

from agent_guard.banc import jouer
from agent_guard.guard import AllowlistInvalide, charger_allowlist, entropie, signaux


class Allowlist(unittest.TestCase):
    def ecrire(self, hotes):
        f = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
        json.dump({"hotes": hotes}, f)
        f.close()
        self.addCleanup(os.remove, f.name)
        return f.name

    def test_exacte(self):
        self.assertEqual(charger_allowlist(self.ecrire(["example.com"])), {"example.com"})

    def test_jokers_et_majuscules_refuses(self):
        for mauvais in (["*.example.com"], ["Example.com"], ["example.com."], [""], [42]):
            with self.assertRaises(AllowlistInvalide, msg=mauvais):
                charger_allowlist(self.ecrire(mauvais))


class Heuristiques(unittest.TestCase):
    def test_requete_banale_sans_signal(self):
        self.assertEqual(signaux("http://example.com/index.html", "example.com", "/index.html", b""), [])

    def test_chaque_signal(self):
        self.assertIn("base64_suspect", signaux("http://h/", "h", "/", b"QUJD" * 12))
        self.assertIn("haute_entropie", signaux("http://h/", "h", "/", bytes(range(256))))
        self.assertIn("exfiltration_chemin", signaux("http://h/", "h", "/" + "ab12" * 10, b""))
        hote = "a" * 40 + ".tunnel.example"
        self.assertIn("exfiltration_hote", signaux(f"http://{hote}/", hote, "/", b""))
        self.assertIn("url_anormale", signaux("http://u:p@h/", "h", "/", b""))
        self.assertIn("url_anormale", signaux("http://h/%2541", "h", "/%2541", b""))

    def test_entropie(self):
        self.assertEqual(entropie(b"aaaa"), 0)
        self.assertAlmostEqual(entropie(bytes(range(256))), 8.0)


class Banc(unittest.TestCase):
    def test_tous_les_cas(self):
        res = jouer()
        echecs = [c for c in res["cas"] if not c["ok"]]
        self.assertEqual(echecs, [])
        self.assertGreaterEqual(len(res["cas"]), 16)


if __name__ == "__main__":
    unittest.main()
