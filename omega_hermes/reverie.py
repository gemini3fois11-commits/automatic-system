"""Rêverie — RESPIRE / DORT / RÊVE / CHOISI (blueprint §6.3).

Quand l'essaim ne surveille rien, il fabrique des signaux jamais vus et BOB les juge
comme tout le reste. L'élection ORDONNE des candidats ; elle ne crée pas de classe.
Promouvoir un rêve exigerait une étude : famille nouvelle, bande de distance mesurée, tests.
"""

import numpy as np

from omega_hermes.commun import Banc, impulsions
from omega_hermes.eyes import fft_radix2
from omega_hermes.twin import CLASSES, MODALITES, N, Flux

FLUX_REVE = 4
FAMILLES = ("chirp_libre", "carre_libre", "impulsions_libres", "melange", "derives_croisees")
SEUIL_PLATITUDE = 0.3     # sous ce seuil, le spectre d'une modalité est structuré (tonal)
SEUIL_XCORR = 0.1


def rever(banc: Banc, rng, famille: str) -> np.ndarray:
    a = banc.alice
    if famille == "chirp_libre":
        return a.chirp(rng)
    if famille == "carre_libre":
        return a.carre(rng)
    if famille == "impulsions_libres":
        x = rng.normal(0, 0.05, (len(MODALITES), N))
        for m in rng.choice(len(MODALITES), size=int(rng.integers(1, 4)), replace=False):
            x[m] += impulsions(rng, rng.uniform(0.3, 1.5), int(rng.integers(8, 64)), int(rng.integers(1, 6)))
        return x
    base = banc.twin.observer(CLASSES[int(rng.integers(0, len(CLASSES)))])
    if famille == "melange":
        return 0.5 * base + 0.5 * a.chirp(rng)
    pente = np.linspace(0, 1, N)
    base[3] += rng.uniform(1, 3) * pente
    base[4] -= rng.uniform(1, 3) * pente
    return base + rng.normal(0, 0.2, base.shape)


def platitude(x: np.ndarray) -> np.ndarray:
    """Platitude spectrale par modalité : 1 pour un bruit blanc, proche de 0 pour une raie."""
    p = np.abs(fft_radix2(x))[..., 1:N // 2 + 1] ** 2 + 1e-20
    return np.exp(np.log(p).mean(-1)) / p.mean(-1)


def cycle(banc: Banc, *, respire=20, dort=10, reve=60, elus=3) -> dict:
    rng = Flux(banc.graine, FLUX_REVE).suivant()
    # RESPIRE — sans souffle stable, la suite ne vaut rien
    nominaux = banc.twin.lot([CLASSES[i % 3] for i in range(respire)])
    d_nom, dist_nom, *_ = banc.juger(nominaux)
    acceptation = float(np.mean([Banc.accepte(d) for d in d_nom]))
    souffle = {"n": respire, "acceptation": acceptation, "distance_moyenne": float(np.mean(dist_nom))}
    if acceptation < 0.9:
        return {"respire": souffle, "interrompu": "souffle_instable"}
    # DORT — des rêves en tampon, sans jugement
    appels = banc.appels_bob
    tampon = [rever(banc, rng, FAMILLES[i % len(FAMILLES)]) for i in range(dort)]
    dort_sans_jugement = banc.appels_bob == appels
    # RÊVE — rêves jugés
    familles = [FAMILLES[i % len(FAMILLES)] for i in range(reve)]
    X = np.stack([rever(banc, rng, f) for f in familles])
    decisions, dmin, T, plat = banc.juger(X)
    reves = []
    for i, (f, d, dist, t, p) in enumerate(zip(familles, decisions, dmin, T, plat)):
        xcorr = float(t[-1])
        structure = bool(platitude(X[i]).min() < SEUIL_PLATITUDE or abs(xcorr) >= SEUIL_XCORR or p)
        etat = "accepte" if Banc.accepte(d) else ("structure" if structure else "bruit")
        ecretage = float((np.diff(X[i], axis=-1) == 0).mean())
        score = abs(xcorr) + 0.5 * ecretage + 0.25 * min(float(dist) / banc.bob.seuil_lache, 2.0)
        reves.append({"indice": i, "famille": f, "decision": d, "etat": etat,
                      "distance": float(dist), "xcorr": xcorr, "ecretage": ecretage, "score": score})
    # CHOISI — élection des meilleurs rêves structurés
    candidats = sorted((r for r in reves if r["etat"] == "structure"), key=lambda r: (-r["score"], r["indice"]))
    compte = {e: sum(r["etat"] == e for r in reves) for e in ("accepte", "structure", "bruit")}
    return {"respire": souffle, "dort": {"n": len(tampon), "sans_jugement": dort_sans_jugement},
            "reve": {"n": reve, **compte,
                     "par_famille": {f: {e: sum(r["etat"] == e for r in reves if r["famille"] == f)
                                         for e in ("accepte", "structure", "bruit")} for f in FAMILLES}},
            "choisi": [{k: r[k] for k in ("indice", "famille", "score", "decision")} for r in candidats[:elus]],
            "reves": reves}
