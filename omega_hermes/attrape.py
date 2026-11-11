"""Attrape (blueprint §6.2) : piège à signaux inconnus. Chaque rejet est mis en quarantaine
avec un motif écrit, chiffré et vérifiable, dans une chaîne Γ."""

from omega_hermes.commun import Banc
from omega_hermes.twin import CLASSES

CHAMPS_MOTIF = ("decision", "distance", "seuil_strict", "seuil_lache", "plateaux", "xcorr", "classe_proche")


def pieger(banc: Banc, journal, n: int = 200) -> dict:
    X, labels, familles = banc.alice.lot(n)
    decisions, dmin, T, plat = banc.juger(X)
    proches = banc.bob.distances(banc.std.transformer(T)).argmin(1)
    rejets = 0
    for lab, fam, d, dist, t, p, k in zip(labels, familles, decisions, dmin, T, plat, proches):
        if Banc.accepte(d):
            continue
        rejets += 1
        journal.inscrire("quarantaine", "QUARANTAINE", d.lower(), {
            "decision": d, "distance": float(dist), "seuil_strict": banc.bob.seuil_strict,
            "seuil_lache": banc.bob.seuil_lache, "plateaux": bool(p), "xcorr": float(t[-1]),
            "classe_proche": CLASSES[int(k)], "famille_banc": fam})
    return {"observations": n, "rejets": rejets}
