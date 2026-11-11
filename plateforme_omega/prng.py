"""PRNG CryoLoop (blueprint §6.2) : xoshiro256** en C++, vérifié depuis Python.

Compilé avec -Wall -Wextra -Werror dans .src/ (brouillons de build, ignorés par git).
Contrôles : vecteur de référence publié de SplitMix64, accord au bit près avec une
implémentation Python indépendante, déterminisme, moments, uniformité (χ²), indépendance
(autocorrélation de rang 1).
"""

import os
import subprocess

import numpy as np

from plateforme_omega.commun import DOSSIER, conclure, sortir

RACINE = os.path.dirname(DOSSIER)
SOURCE = os.path.join(DOSSIER, "prng", "cryoloop_prng.cpp")
BINAIRE = os.path.join(RACINE, ".src", "prng", "cryoloop_prng")
M64 = (1 << 64) - 1
# SplitMix64, graine 0 : premières sorties de l'implémentation de référence de Vigna.
SPLITMIX_GRAINE_0 = ("e220a8397b1dcdaf", "6e789e6aa1b965f4", "06c45d188009454f")


def compiler() -> str:
    os.makedirs(os.path.dirname(BINAIRE), exist_ok=True)
    r = subprocess.run(["g++", "-std=c++17", "-O2", "-Wall", "-Wextra", "-Werror", "-pedantic",
                        SOURCE, "-o", BINAIRE], capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(r.stderr)
    return r.stderr


def tirer(graine: int, n: int, mode: str = "") -> list[str]:
    args = [BINAIRE, str(graine), str(n)] + ([mode] if mode else [])
    return subprocess.run(args, capture_output=True, text=True, check=True).stdout.split()


def xoshiro_python(graine: int, n: int) -> list[int]:
    def splitmix(x):
        x = (x + 0x9E3779B97F4A7C15) & M64
        z = x
        z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & M64
        z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & M64
        return x, z ^ (z >> 31)

    rotl = lambda v, k: ((v << k) | (v >> (64 - k))) & M64
    s, x = [], graine
    for _ in range(4):
        x, v = splitmix(x)
        s.append(v)
    sortie = []
    for _ in range(n):
        sortie.append((rotl((s[1] * 5) & M64, 7) * 9) & M64)
        t = (s[1] << 17) & M64
        s[2] ^= s[0]; s[3] ^= s[1]; s[1] ^= s[2]; s[0] ^= s[3]; s[2] ^= t
        s[3] = rotl(s[3], 45)
    return sortie


def mesurer(graine=7, n=200_000) -> dict:
    avertissements = compiler()
    u = np.array([float(v) for v in tirer(graine, n)])
    compte, _ = np.histogram(u, bins=100, range=(0, 1))
    attendu = n / 100
    return {"compilation": "g++ -std=c++17 -O2 -Wall -Wextra -Werror -pedantic",
            "avertissements": avertissements, "n": n,
            "splitmix_reference": tirer(0, 3, "--splitmix") == list(SPLITMIX_GRAINE_0),
            "accord_python_bits": [int(v, 16) for v in tirer(graine, 2000, "--brut")] == xoshiro_python(graine, 2000),
            "deterministe": tirer(graine, 1000) == tirer(graine, 1000),
            "graines_distinctes": tirer(graine, 50) != tirer(graine + 1, 50),
            "moyenne": float(u.mean()), "variance": float(u.var()),
            "chi2_100_classes": float(((compte - attendu) ** 2 / attendu).sum()),
            "R_autocorrelation_rang_1": float(np.corrcoef(u[:-1], u[1:])[0, 1])}


def main() -> int:
    m = mesurer()
    n = m["n"]
    return conclure("prng", [
        ("compile sans aucun avertissement (-Wall -Wextra -Werror -pedantic)", m["avertissements"] == "", ""),
        ("SplitMix64 : vecteur de référence publié (graine 0)", m["splitmix_reference"], ""),
        ("xoshiro256** : accord au bit près avec l'implémentation Python (2000 tirages)", m["accord_python_bits"], ""),
        ("déterministe, et deux graines donnent deux suites", m["deterministe"] and m["graines_distinctes"], ""),
        ("moyenne à 4 σ de 1/2", abs(m["moyenne"] - 0.5) < 4 * np.sqrt(1 / 12 / n), f"{m['moyenne']:.5f}"),
        ("variance proche de 1/12", abs(m["variance"] - 1 / 12) < 0.002, f"{m['variance']:.5f}"),
        ("χ² à 99 degrés de liberté sous le seuil 0,001 (148,2)", m["chi2_100_classes"] < 148.2,
         f"{m['chi2_100_classes']:.1f}"),
        ("autocorrélation de rang 1 à 4 σ de 0", abs(m["R_autocorrelation_rang_1"]) < 4 / np.sqrt(n),
         f"R = {m['R_autocorrelation_rang_1']:.5f}"),
    ], m, ["Non cryptographique : ne jamais l'utiliser pour une clé, un jeton ou un sel.",
           "Batterie statistique élémentaire, pas TestU01 ni PractRand."])


if __name__ == "__main__":
    sortir(main())
