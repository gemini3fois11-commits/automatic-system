import contextlib
import io
import json
import os
import tempfile
import unittest

from rinv.systeme import executer


class SystemeTest(unittest.TestCase):
    def test_demonstration_de_bout_en_bout(self):
        with tempfile.TemporaryDirectory() as tmp:
            chemin = os.path.join(tmp, "systeme_evidence.json")
            with contextlib.redirect_stdout(io.StringIO()):
                code = executer(chemin)
            with open(chemin, encoding="utf-8") as fh:
                ev = json.load(fh)
        echecs = [c for c in ev["mesures"]["controles"] if not c["ok"]]
        self.assertEqual(code, 0, echecs)
        self.assertEqual(ev["verdict"], "OK")
        self.assertEqual([a["exit_temoin"] for a in ev["mesures"]["attaques"]], [4, 4])
        self.assertEqual([a["exit_local"] for a in ev["mesures"]["attaques"]], [0, 0])
        self.assertGreater(ev["mesures"]["journal"]["refus_prouves"], 0)


if __name__ == "__main__":
    unittest.main()
