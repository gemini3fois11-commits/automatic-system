"""HYPER — poids virtuels (blueprint §6.6) : les poids ne sont jamais stockés.

w(i) = √(2/K) · Σ_k a_k · sin(2π f_k i + φ_k), K = 64 oscillateurs : 192 nombres
stockés génèrent autant de poids qu'on veut. On compare un ELM (extreme learning
machine) dont les poids cachés sont virtuels à un ELM aux poids stockés, sur les
traits HERMÈS des trois régimes connus.
"""

import time

import numpy as np

from omega_hermes.eyes import Standardiseur, traits
from omega_hermes.twin import CLASSES, Twin
from plateforme_omega.commun import conclure, sortir

K = 64


class Oscillateurs:
    def __init__(self, rng, k=K):
        self.a = rng.normal(size=k)
        self.f = rng.uniform(0, 0.5, size=k)
        self.phi = rng.uniform(0, 2 * np.pi, size=k)

    @property
    def stockes(self) -> int:
        return self.a.size + self.f.size + self.phi.size

    def poids(self, i) -> np.ndarray:
        i = np.asarray(i, dtype=float)
        return np.sqrt(2 / K) * (self.a * np.sin(2 * np.pi * self.f * i[..., None] + self.phi)).sum(-1)


def elm(W, Z, Y, Z_test):
    H = np.tanh(Z @ W)
    beta = np.linalg.lstsq(H, Y, rcond=None)[0]
    return np.tanh(Z_test @ W) @ beta


def mesurer(graine=7) -> dict:
    rng = np.random.default_rng(graine)
    osc = Oscillateurs(rng)
    n_virtuels = 1_000_000
    t0 = time.perf_counter()
    w = osc.poids(np.arange(n_virtuels))
    duree = time.perf_counter() - t0
    twin = Twin(graine)
    cl_tr = [CLASSES[i % 3] for i in range(300)]
    cl_te = [CLASSES[i % 3] for i in range(200)]
    std = Standardiseur().ajuster(traits(twin.lot(cl_tr)))
    Z, Zt = std.transformer(traits(twin.lot(cl_tr))), std.transformer(traits(twin.lot(cl_te)))
    Y = np.eye(3)[[CLASSES.index(c) for c in cl_tr]]
    cachees = 256
    W_virtuel = osc.poids(np.arange(31 * cachees)).reshape(31, cachees)
    W_stocke = rng.normal(size=(31, cachees))
    vraies = np.array([CLASSES.index(c) for c in cl_te])
    exact = lambda W: float((elm(W, Z, Y, Zt).argmax(1) == vraies).mean())
    return {"nombres_stockes": osc.stockes, "poids_virtuels": n_virtuels,
            "compression": n_virtuels / osc.stockes, "variance": float(w.var()),
            "moyenne": float(w.mean()), "generation_s": duree,
            "elm_virtuel": exact(W_virtuel), "elm_stocke": exact(W_stocke), "tests": len(cl_te)}


def main() -> int:
    m = mesurer()
    return conclure("hyper", [
        ("192 nombres stockés", m["nombres_stockes"] == 192, ""),
        ("1 000 000 de poids virtuels générés", m["poids_virtuels"] == 1_000_000, f"×{m['compression']:.0f}"),
        ("variance dans la bande [0,5 ; 2]", 0.5 <= m["variance"] <= 2.0, f"{m['variance']:.3f}"),
        ("ELM virtuel aussi exact que l'ELM stocké (± 0,02)", abs(m["elm_virtuel"] - m["elm_stocke"]) <= 0.02,
         f"{m['elm_virtuel']:.3f} vs {m['elm_stocke']:.3f} sur {m['tests']} tests"),
    ], m | {"gain": m["compression"]},
        ["Les poids virtuels ne sont pas indépendants : 64 oscillateurs, donc un rang limité.",
         "ELM évalué sur des traits synthétiques HERMÈS, tâche facile ; rien sur un réseau profond."])


if __name__ == "__main__":
    sortir(main())
