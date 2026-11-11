"""Tail-Call Topological Collapse (TCTC) : repli torique de la pile.

Une fonction décorée par `@torus()` peut s'appeler elle-même en position
terminale sans faire croître la pile au-delà du seuil ρ_c. Quand la profondeur
atteint ρ_c, aucun nouveau cadre n'est alloué : les arguments (accumulateurs)
sont réinjectés au point d'entrée et la profondeur retombe à zéro.

Limite assumée : le repli jette les cadres intermédiaires, il n'est donc correct
que si l'appel récursif est terminal (`return f(...)`), c'est-à-dire si tout
l'état utile voyage dans les arguments. `1 + f(n - 1)` n'est pas repliable.
"""

import functools
import sys
import threading

RHO_C = 888   # facteur de repli cyclique
EPSILON = 64  # marge ε sous la limite matérielle Ω_H


class _Fold(BaseException):
    def __init__(self, args, kwargs):
        self.call = (args, kwargs)


def _frame_depth() -> int:
    frame, depth = sys._getframe(1), 0
    while frame is not None:
        frame, depth = frame.f_back, depth + 1
    return depth


def torus(rho_c: int = RHO_C):
    """Décorateur : ρ_c effectif = min(rho_c, (Ω_H − ε) / 2)."""
    if rho_c < 1:
        raise ValueError("rho_c doit être ≥ 1")

    def decorate(fn):
        local = threading.local()

        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            if getattr(local, "active", False):
                if local.rho >= local.rho_c:
                    raise _Fold(args, kwargs)
                local.rho += 1
                return fn(*args, **kwargs)

            # Point d'entrée : chaque niveau coûte deux cadres (wrapper + fn).
            headroom = (sys.getrecursionlimit() - _frame_depth() - EPSILON) // 2
            local.active, local.rho, local.rho_c = True, 0, max(1, min(rho_c, headroom))
            folds = 0
            try:
                while True:
                    try:
                        return fn(*args, **kwargs)
                    except _Fold as fold:
                        args, kwargs = fold.call
                        local.rho = 0
                        folds += 1
            finally:
                local.active = False
                wrapper.folds = folds

        wrapper.folds = 0
        return wrapper

    return decorate
