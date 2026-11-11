"""MTD — défense par cible mouvante (blueprint §6.5), 7 niveaux.

Cinq surfaces portent un secret dérivé par époque : clés (Ed25519 réelle), topologie,
identifiants, routes, nœud (dérivés HMAC). Un niveau fait tourner les surfaces jusqu'à
lui (cumulatif) ; Ω fait tourner tout, à chaque période. L'attaquant capture le secret
d'une surface au hasard et a besoin de 3 périodes pour l'exploiter : il réussit si le
secret capturé est encore valide 3 périodes plus tard. La validité est vérifiée par le
vrai mécanisme (signature Ed25519 vérifiée, égalité HMAC), pas par une formule.

[SIMULÉ] : l'attaquant, le temps et les coûts sont modélisés.
"""

import hashlib
import hmac

import numpy as np

from plateforme_omega.commun import conclure, sortir
from plateforme_omega.omega_q import evaluer
from socle_preuve import ed25519

SURFACES = ("cles", "topologie", "identifiants", "routes", "noeud")
COUT_ROTATION = {"cles": 0.05, "topologie": 0.10, "identifiants": 0.02, "routes": 0.05, "noeud": 0.20}
NIVEAUX = {"0": (), "1": SURFACES[:1], "2": SURFACES[:2], "3": SURFACES[:3], "4": SURFACES[:4],
           "5": SURFACES, "Ω": SURFACES}
FENETRE = 3


class Cible:
    def __init__(self, niveau: str, periode: int, racine: bytes):
        self.tournantes = set(NIVEAUX[niveau])
        self.periode = 1 if niveau == "Ω" else periode
        self.racine = racine
        self._cles = {}

    def epoque(self, surface: str, t: int) -> int:
        return t // self.periode if surface in self.tournantes else 0

    def secret(self, surface: str, t: int) -> bytes:
        return hmac.new(self.racine, f"{surface}|{self.epoque(surface, t)}".encode(), hashlib.sha256).digest()

    def cle_publique(self, t: int) -> bytes:
        e = self.epoque("cles", t)
        if e not in self._cles:
            self._cles[e] = ed25519.cle_publique(self.secret("cles", t))
        return self._cles[e]

    def attaque_reussit(self, surface: str, capture: int) -> bool:
        exploitation = capture + FENETRE
        if surface == "cles":
            vole = self.secret("cles", capture)                      # la graine privée capturée
            message = b"commande-attaquant"
            return ed25519.verifier(self.cle_publique(exploitation), message, ed25519.signer(vole, message))
        return hmac.compare_digest(self.secret(surface, capture), self.secret(surface, exploitation))


def simuler(niveau: str, periode: int, attaques: int, rng) -> dict:
    cible = Cible(niveau, periode, rng.bytes(32))
    reussites = 0
    for _ in range(attaques):
        reussites += cible.attaque_reussit(SURFACES[int(rng.integers(0, 5))], int(rng.integers(0, 1000)))
    succes = reussites / attaques
    cout = min(sum(COUT_ROTATION[s] for s in cible.tournantes) / cible.periode * (1.5 if niveau == "Ω" else 1), 1)
    q = evaluer(taux_echec=succes, gain=1 / succes if succes else 1000.0,
                reprise=len(cible.tournantes) / len(SURFACES), loc=0, runtime_s=0,
                cout_direct=cout, attaquant_reussi=succes > 0)
    return {"niveau": niveau, "periode": cible.periode, "succes_attaquant": succes, "cout": cout} | q


def mesurer(graine=7, attaques=300) -> dict:
    rng = np.random.default_rng(graine)
    lignes = [simuler(n, p, attaques, rng) for n in NIVEAUX for p in ((1, 5) if n != "Ω" else (1,))]
    acceptes = [l for l in lignes if l["decision"] == "ACCEPTER"]
    meilleur = max(acceptes, key=lambda l: l["Q"]) if acceptes else None
    return {"fenetre_attaquant": FENETRE, "attaques_par_config": attaques, "configurations": lignes,
            "meilleur_Q": meilleur}


def main() -> int:
    m = mesurer()
    c = {(l["niveau"], l["periode"]): l for l in m["configurations"]}
    return conclure("mtd", [
        ("niveau 0 : l'attaquant réussit toujours, veto REJETER",
         c[("0", 1)]["succes_attaquant"] == 1.0 and c[("0", 1)]["decision"] == "REJETER", ""),
        ("rotation complète, période 1 ≤ fenêtre : l'attaquant échoue",
         c[("5", 1)]["succes_attaquant"] == 0.0 and c[("Ω", 1)]["succes_attaquant"] == 0.0, ""),
        ("période 5 > fenêtre 3 : l'attaquant réussit, veto", c[("5", 5)]["succes_attaquant"] > 0
         and c[("5", 5)]["decision"] == "REJETER", f"succès {c[('5', 5)]['succes_attaquant']:.2f}"),
        ("rotation partielle contournée : l'attaquant vise une surface fixe",
         all(c[(n, 1)]["decision"] == "REJETER" for n in ("1", "2", "3", "4")),
         ", ".join(f"niveau {n} : {c[(n, 1)]['succes_attaquant']:.2f}" for n in ("1", "2", "3", "4"))),
        ("Ω le plus sûr et le plus cher", c[("Ω", 1)]["cout"] >= max(l["cout"] for l in m["configurations"]),
         f"coût {c[('Ω', 1)]['cout']:.2f}"),
    ], m, ["Attaquant modélisé : il capture un secret et a besoin de 3 périodes ; pas d'attaque adaptative.",
           "Le blueprint annonce le niveau 1 comme meilleur Q ; ici, toute rotation partielle est contournée "
           "par un attaquant qui vise une surface fixe. Les deux modèles d'attaquant diffèrent.",
           "Coûts de rotation déclarés à la main."], etiquette="SIMULÉ")


if __name__ == "__main__":
    sortir(main())
