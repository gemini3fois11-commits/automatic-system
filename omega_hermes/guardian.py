"""Guardian — dynamique de frappe par CATÉGORIES et TIMINGS uniquement (blueprint §6.2, §10.3).

Ligne rouge : jamais les caractères. L'entrée n'accepte que des événements
{categorie, t_appui_ms, t_relache_ms} ; tout autre champ est refusé à l'entrée, avant
tout calcul. Il n'existe dans ce module aucun moyen de lire un clavier : il reçoit des
événements déjà abstraits, ici synthétiques.

Signaux : frappe robotique (intervalles trop réguliers), injection (rafale plus rapide
qu'une main), effacements anormaux. Ce dernier n'est pas un seuil fixe : c'est un test
binomial contre un taux humain de base déclaré, dont le seuil dépend de la longueur du flux.
"""

import statistics

import numpy as np

CATEGORIES = frozenset({"lettre", "chiffre", "espace", "ponctuation", "controle", "effacement"})
CHAMPS = frozenset({"categorie", "t_appui_ms", "t_relache_ms"})
CV_ROBOTIQUE = 0.05      # coefficient de variation des intervalles sous lequel c'est une machine
VOL_INJECTION_MS = 15    # intervalle médian sous lequel aucune main ne tape
TAUX_EFFACEMENT_HUMAIN = 0.05   # hypothèse déclarée : une frappe humaine efface ~5 % du temps
SIGMAS = 3


class EvenementRefuse(ValueError):
    pass


def valider(evenements) -> list[dict]:
    propres = []
    for e in evenements:
        if not isinstance(e, dict) or set(e) != CHAMPS:
            raise EvenementRefuse("champs autorisés : categorie, t_appui_ms, t_relache_ms — jamais de caractère")
        if e["categorie"] not in CATEGORIES:
            raise EvenementRefuse(f"catégorie inconnue : {e['categorie']!r}")
        if not (isinstance(e["t_appui_ms"], (int, float)) and isinstance(e["t_relache_ms"], (int, float))
                and e["t_relache_ms"] >= e["t_appui_ms"]):
            raise EvenementRefuse("horodatages invalides")
        propres.append(dict(e))
    return propres


def analyser(evenements) -> dict:
    ev = valider(evenements)
    if len(ev) < 10:
        return {"evenements": len(ev), "verdict": "INSUFFISANT", "signaux": []}
    appuis = np.array([e["t_appui_ms"] for e in ev], dtype=float)
    maintiens = np.array([e["t_relache_ms"] - e["t_appui_ms"] for e in ev], dtype=float)
    vols = np.diff(appuis)
    cv = float(vols.std() / vols.mean()) if vols.mean() > 0 else 0.0
    effacements = sum(e["categorie"] == "effacement" for e in ev) / len(ev)
    signaux = []
    if cv < CV_ROBOTIQUE:
        signaux.append("frappe_robotique")
    if statistics.median(vols) < VOL_INJECTION_MS:
        signaux.append("injection_rafale")
    p0 = TAUX_EFFACEMENT_HUMAIN
    seuil_effacement = p0 + SIGMAS * float(np.sqrt(p0 * (1 - p0) / len(ev)))
    if effacements > seuil_effacement:
        signaux.append("effacements_anormaux")
    return {"evenements": len(ev), "vol_median_ms": float(np.median(vols)),
            "maintien_median_ms": float(np.median(maintiens)), "cv_vols": cv,
            "taux_effacement": effacements, "seuil_effacement": seuil_effacement, "signaux": signaux,
            "verdict": "SIGNALER" if signaux else "NORMAL"}


def synthetique(rng, profil: str, n: int = 80) -> list[dict]:
    """Flux d'événements synthétiques : humain, robot, injection, hésitation."""
    cats = rng.choice(["lettre"] * 8 + ["espace", "ponctuation"], size=n).tolist()
    if profil == "humain":
        vols, maintiens = rng.lognormal(np.log(180), 0.35, n), rng.normal(95, 20, n)
        cats = [("effacement" if rng.random() < TAUX_EFFACEMENT_HUMAIN else c) for c in cats]
    elif profil == "robot":
        vols, maintiens = np.full(n, 120.0) + rng.normal(0, 1, n), np.full(n, 50.0)
    elif profil == "injection":
        vols, maintiens = rng.uniform(1, 6, n), np.full(n, 2.0)
    else:  # hésitation
        vols, maintiens = rng.lognormal(np.log(260), 0.5, n), rng.normal(110, 25, n)
        cats = [("effacement" if rng.random() < 0.45 else c) for c in cats]
    t, ev = 0.0, []
    for c, v, m in zip(cats, vols, np.maximum(maintiens, 1)):
        t += float(v)
        ev.append({"categorie": c, "t_appui_ms": t, "t_relache_ms": t + float(m)})
    return ev
