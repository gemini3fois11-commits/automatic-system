"""Métrologie inversée : charge d'infrastructure Ω_infra et stabilité S_g⁻¹."""

import math
from typing import Iterable, Mapping, NamedTuple, Sequence


def inverse_sum(healths: Iterable[float]) -> float:
    """S_g⁻¹ = Σ 1/n_k, avec n_k ∈ [0, 1]. Un nœud effondré (n_k = 0) donne +∞."""
    total = 0.0
    for n in healths:
        if not 0.0 <= n <= 1.0:
            raise ValueError(f"indice de santé hors de [0, 1] : {n!r}")
        if n == 0.0:
            return math.inf
        total += 1.0 / n
    return total


class Diagnosis(NamedTuple):
    inverse_sum: float   # S_g⁻¹ ; vaut N quand tous les nœuds sont à 1
    excess: float        # S_g⁻¹ − N : 0 au nominal, croît avec la dégradation
    weakest: str | None  # nœud qui domine la somme
    weakest_health: float | None


def diagnose(nodes: Mapping[str, float]) -> Diagnosis:
    """Identifie le point de rupture le plus faible du cluster."""
    s = inverse_sum(nodes.values())
    if not nodes:
        return Diagnosis(0.0, 0.0, None, None)
    weakest = min(nodes, key=nodes.__getitem__)
    return Diagnosis(s, s - len(nodes), weakest, nodes[weakest])


def infra_load(
    samples: Sequence[tuple[float, float, float, float]],
    alpha: float = 1.0,
    beta: float = 1.0,
    gamma: float = 1.0,
) -> float:
    """Ω_infra(t) = ∫ [α·A(τ) + β·M(τ) + γ·D(τ)] dτ, par la méthode des trapèzes.

    `samples` : suite de (τ, A, M, D) à τ strictement croissant.
    """
    total = 0.0
    for (t0, a0, m0, d0), (t1, a1, m1, d1) in zip(samples, samples[1:]):
        if t1 <= t0:
            raise ValueError("les instants τ doivent être strictement croissants")
        f0 = alpha * a0 + beta * m0 + gamma * d0
        f1 = alpha * a1 + beta * m1 + gamma * d1
        total += (f0 + f1) * (t1 - t0) / 2.0
    return total


def efficiency(phi: float, omega_infra: float) -> float:
    """S = Φ / Ω_infra."""
    return math.inf if omega_infra == 0 else phi / omega_infra
