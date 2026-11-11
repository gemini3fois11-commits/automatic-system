"""Compte analytique des opérations flottantes d'une décision HERMÈS (estimation déclarée)."""

import math


def flops_par_decision(modalites: int, n: int, traits: int, classes: int) -> float:
    fft = modalites * 5 * n * math.log2(n)          # ~5 N log2 N par FFT complexe radix-2
    descripteurs = modalites * 12 * n               # moyenne, écart-type, crête, kurtosis, spectre
    correlation = 4 * n
    distances = classes * traits * 3
    return float(fft + descripteurs + correlation + distances)
