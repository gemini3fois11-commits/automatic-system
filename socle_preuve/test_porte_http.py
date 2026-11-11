import http.client
import threading
import unittest

from socle_preuve.porte_http import DRAIN_MAX_OCTETS, Gestionnaire, Serveur


class Porte(Gestionnaire):
    def do_POST(self):
        if not self.controle_hote():
            return
        corps = self.lire_json()
        if corps is None:
            return
        self.repondre_json(200, {"ok": True})


class FermetureDifferee(unittest.TestCase):
    """Régression : une erreur renvoyée sans lire le corps ne doit jamais devenir un
    BrokenPipe ou un ConnectionReset côté client, même sous 40 envois simultanés."""

    def setUp(self):
        self.s = Serveur(0, Porte)
        threading.Thread(target=self.s.serve_forever, daemon=True).start()
        self.addCleanup(self.s.server_close)
        self.addCleanup(self.s.shutdown)
        self.port = self.s.server_address[1]

    def rafale(self, corps: bytes, hote: str, n: int = 40):
        codes, erreurs = [], []

        def envoyer():
            try:
                c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=15)
                c.request("POST", "/", body=corps, headers={"Host": hote})
                r = c.getresponse()
                r.read()
                codes.append(r.status)
                c.close()
            except OSError as e:
                erreurs.append(type(e).__name__)

        fils = [threading.Thread(target=envoyer) for _ in range(n)]
        for f in fils:
            f.start()
        for f in fils:
            f.join()
        return codes, erreurs

    def test_corps_trop_gros(self):
        codes, erreurs = self.rafale(b"x" * (1024 * 1024), f"127.0.0.1:{self.port}")
        self.assertEqual((erreurs, codes), ([], [413] * 40))

    def test_hote_refuse_avec_gros_corps(self):
        codes, erreurs = self.rafale(b"x" * (1024 * 1024), "attaquant.example")
        self.assertEqual((erreurs, codes), ([], [421] * 40))

    def test_corps_demesure_borne_assumee(self):
        """Au-delà de DRAIN_MAX_OCTETS, le client peut voir une réinitialisation : c'est la borne
        déclarée. Ce qui est exigé : le serveur n'y laisse aucun fil bloqué et répond encore."""
        codes, erreurs = self.rafale(b"x" * (4 * DRAIN_MAX_OCTETS), "attaquant.example", n=8)
        self.assertEqual(len(codes) + len(erreurs), 8)
        self.assertTrue(set(codes) <= {421})
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        c.request("POST", "/", body=b"{}", headers={"Host": f"127.0.0.1:{self.port}"})
        self.assertEqual(c.getresponse().status, 200)
        c.close()

    def test_requete_normale_garde_la_connexion(self):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        for _ in range(3):                                  # trois requêtes sur la même connexion
            c.request("POST", "/", body=b'{"a": 1}', headers={"Host": f"127.0.0.1:{self.port}"})
            r = c.getresponse()
            self.assertEqual((r.status, r.read()), (200, b'{"ok": true}'))
            self.assertIsNone(r.getheader("Connection"))
        c.close()


if __name__ == "__main__":
    unittest.main()
