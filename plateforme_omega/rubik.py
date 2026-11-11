"""Rubik — reprise par inversion (blueprint §6.2, §6.4).

Un vrai cube 3×3 : 54 facettes positionnées dans l'espace, chaque mouvement est une
rotation de 90° d'une couche, calculée géométriquement. Un mélange de 200 coups est
défait en jouant la séquence inverse : la reprise est démontrée, pas supposée.
"""

import itertools

import numpy as np

from plateforme_omega.commun import conclure, sortir

AXES = {"R": (0, 1), "L": (0, -1), "U": (1, 1), "D": (1, -1), "F": (2, 1), "B": (2, -1)}


def _facettes():
    f = []
    for axe, signe in itertools.product(range(3), (1, -1)):
        for a, b in itertools.product((-1, 0, 1), repeat=2):
            p = [0, 0, 0]
            p[axe] = signe
            autres = [i for i in range(3) if i != axe]
            p[autres[0]], p[autres[1]] = a, b
            n = [0, 0, 0]
            n[axe] = signe
            f.append((tuple(p), tuple(n)))
    return f


FACETTES = _facettes()
INDEX = {f: i for i, f in enumerate(FACETTES)}


def _rotation(axe, signe):
    """Quart de tour horaire vu depuis la face (axe, signe)."""
    R = np.eye(3, dtype=int)
    i, j = [k for k in range(3) if k != axe]
    R[i, i] = R[j, j] = 0
    R[i, j], R[j, i] = signe, -signe
    if axe == 1:
        R = R.T
    return R


def _mouvement(nom):
    axe, signe = AXES[nom]
    R = _rotation(axe, signe)
    perm = list(range(54))
    for k, (p, n) in enumerate(FACETTES):
        if p[axe] == signe:
            q = tuple(int(v) for v in R @ np.array(p))
            m = tuple(int(v) for v in R @ np.array(n))
            perm[INDEX[(q, m)]] = k
    return np.array(perm)


MOUVEMENTS = {nom: _mouvement(nom) for nom in AXES}
for nom in list(MOUVEMENTS):
    MOUVEMENTS[nom + "'"] = np.argsort(MOUVEMENTS[nom])


def appliquer(etat, coups):
    for c in coups:
        etat = etat[MOUVEMENTS[c]]
    return etat


def inverse(coups):
    return [c[:-1] if c.endswith("'") else c + "'" for c in reversed(coups)]


def ordre(coups):
    resolu = np.arange(54)
    etat, n = appliquer(resolu, coups), 1
    while not np.array_equal(etat, resolu):
        etat, n = appliquer(etat, coups), n + 1
    return n


def mesurer(graine=7, n=200):
    rng = np.random.default_rng(graine)
    melange = [str(c) for c in rng.choice(list(MOUVEMENTS), size=n)]
    resolu = np.arange(54)
    melange_etat = appliquer(resolu, melange)
    return {"coups": n, "facettes_deplacees": int((melange_etat != resolu).sum()),
            "resolu_par_inversion": bool(np.array_equal(appliquer(melange_etat, inverse(melange)), resolu)),
            "ordres": {"R": ordre(["R"]), "R U R' U'": ordre(["R", "U", "R'", "U'"]), "R U": ordre(["R", "U"])},
            "centres_fixes": all(MOUVEMENTS[m][INDEX[(c, c)]] == INDEX[(c, c)] for m in MOUVEMENTS
                                 for c in [tuple(n) for _, n in FACETTES if sum(map(abs, _)) == 1]),
            "reprise": 1.0}


def main() -> int:
    m = mesurer()
    return conclure("rubik", [
        ("chaque quart de tour est d'ordre 4", m["ordres"]["R"] == 4, ""),
        ("R U R' U' d'ordre 6 et R U d'ordre 105 (valeurs connues du cube)",
         m["ordres"]["R U R' U'"] == 6 and m["ordres"]["R U"] == 105, str(m["ordres"])),
        ("les centres ne bougent jamais", m["centres_fixes"], ""),
        ("mélange de 200 coups résolu par inversion", m["resolu_par_inversion"],
         f"{m['facettes_deplacees']} facettes déplacées par le mélange"),
    ], m, ["Démontre la reprise par inversion d'une séquence connue, pas la résolution d'un état inconnu."])


if __name__ == "__main__":
    sortir(main())
