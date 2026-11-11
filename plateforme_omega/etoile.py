"""Algèbre étoilée (blueprint §6.6) : *-algèbre des matrices complexes, involution = adjoint.

[DÉMONTRÉ] pour l'algèbre (axiomes vérifiés numériquement), [SPÉCIFIÉ] pour son
application à HERMÈS : le verdict de BOB comme projection, le sceau comme conjugaison
unitaire. La non-commutativité mesurée dit que « sceller puis vérifier » n'est pas
« vérifier puis sceller ».
"""

import numpy as np

from plateforme_omega.commun import conclure, sortir


def adj(A):
    return A.conj().T


def dft(n):
    k = np.arange(n)
    return np.exp(-2j * np.pi * np.outer(k, k) / n) / np.sqrt(n)


def mesurer(graine=7, n=8, essais=50) -> dict:
    rng = np.random.default_rng(graine)
    c = lambda: rng.normal(size=(n, n)) + 1j * rng.normal(size=(n, n))
    erreurs = {"involutive": 0.0, "antimultiplicative": 0.0, "antilineaire": 0.0, "additive": 0.0,
               "identite_C*": 0.0}
    for _ in range(essais):
        A, B, lam = c(), c(), complex(*rng.normal(size=2))
        erreurs["involutive"] = max(erreurs["involutive"], np.abs(adj(adj(A)) - A).max())
        erreurs["antimultiplicative"] = max(erreurs["antimultiplicative"], np.abs(adj(A @ B) - adj(B) @ adj(A)).max())
        erreurs["antilineaire"] = max(erreurs["antilineaire"], np.abs(adj(lam * A) - lam.conjugate() * adj(A)).max())
        erreurs["additive"] = max(erreurs["additive"], np.abs(adj(A + B) - (adj(A) + adj(B))).max())
        na = np.linalg.norm(A, 2)
        erreurs["identite_C*"] = max(erreurs["identite_C*"], abs(np.linalg.norm(adj(A) @ A, 2) - na ** 2) / na ** 2)
    F = dft(8)
    x = rng.normal(size=8) + 1j * rng.normal(size=8)
    unitaire = np.abs(F @ adj(F) - np.eye(8)).max()
    parseval = abs(np.linalg.norm(F @ x) ** 2 - np.linalg.norm(x) ** 2)
    # Verdict comme projection orthogonale (P = P² = P*), sceau comme conjugaison unitaire.
    v = rng.normal(size=(n, 2)) + 1j * rng.normal(size=(n, 2))
    Q, _ = np.linalg.qr(v)
    P = Q @ adj(Q)
    projection = max(np.abs(P @ P - P).max(), np.abs(adj(P) - P).max())
    U, _ = np.linalg.qr(c())
    H = c()
    H = H + adj(H)
    spectre = np.abs(np.sort(np.linalg.eigvalsh(U @ H @ adj(U))) - np.sort(np.linalg.eigvalsh(H))).max()
    commutateur = float(np.linalg.norm(P @ U - U @ P))
    return {"erreurs_axiomes": {k: float(v) for k, v in erreurs.items()}, "dft8_unitaire": float(unitaire),
            "parseval": float(parseval), "projection": float(projection), "spectre_conserve": float(spectre),
            "commutateur_verdict_sceau": commutateur}


def main() -> int:
    m = mesurer()
    tol = 1e-12
    return conclure("etoile", [
        ("axiomes de *-algèbre (involutive, antimultiplicative, antilinéaire, additive)",
         max(v for k, v in m["erreurs_axiomes"].items() if k != "identite_C*") < tol,
         f"erreur max {max(m['erreurs_axiomes'].values()):.2e}"),
        ("identité C* : ‖A*A‖ = ‖A‖²", m["erreurs_axiomes"]["identite_C*"] < 1e-10, ""),
        ("DFT-8 unitaire et Parseval", m["dft8_unitaire"] < tol and m["parseval"] < 1e-10,
         f"{m['dft8_unitaire']:.2e} / {m['parseval']:.2e}"),
        ("verdict = projection (P² = P = P*)", m["projection"] < tol, f"{m['projection']:.2e}"),
        ("sceau = conjugaison unitaire, spectre conservé", m["spectre_conserve"] < 1e-10, f"{m['spectre_conserve']:.2e}"),
        ("sceller puis vérifier ≠ vérifier puis sceller", m["commutateur_verdict_sceau"] > 0.1,
         f"‖PU − UP‖ = {m['commutateur_verdict_sceau']:.3f}"),
    ], m, ["Algèbre vérifiée numériquement en double précision, pas prouvée formellement.",
           "Application à HERMÈS [SPÉCIFIÉE] : aucune décision réelle n'en dépend."], etiquette="DÉMONTRÉ")


if __name__ == "__main__":
    sortir(main())
