import http.client
import os
import tempfile
import threading
import unittest

from agent_guard.guard import construire


class CorpsRefuseSousCharge(unittest.TestCase):
    """Régression : un 413 envoyé sans lire le corps ne doit jamais se transformer en
    BrokenPipe côté client (RST du noyau). 40 envois concurrents de 1 Mio + 1 octet."""

    def test_413_toujours_recu(self):
        with tempfile.TemporaryDirectory() as tmp:
            s = construire(0, journal=os.path.join(tmp, "j.jsonl"), connecter=lambda h, p: None)
            threading.Thread(target=s.serve_forever, daemon=True).start()
            port, codes, erreurs = s.server_address[1], [], []

            def envoyer():
                try:
                    c = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
                    c.request("POST", "http://example.com/", body=b"x" * (1024 * 1024 + 1))
                    codes.append(c.getresponse().status)
                    c.close()
                except OSError as e:
                    erreurs.append(type(e).__name__)

            fils = [threading.Thread(target=envoyer) for _ in range(40)]
            for f in fils:
                f.start()
            for f in fils:
                f.join()
            s.shutdown()
            s.server_close()
        self.assertEqual(erreurs, [])
        self.assertEqual(codes, [413] * 40)


if __name__ == "__main__":
    unittest.main()
