"""Mode IA (blueprint §4.2) : chaque agent décide ACCEPTER / SIGNALER / QUARANTAINE et écrit
son hypothèse. Chaque décision est inscrite dans une chaîne Γ.

Politique, explicite :
- BOB accepte une classe connue → ACCEPTER ;
- BOB dit UNKNOWN → QUARANTAINE, même si le signal a des plateaux ;
- BOB dit ARTIFACT et le signal a des plateaux → SIGNALER (hypothèse : capteur défaillant) ;
- BOB dit ARTIFACT sans plateau → QUARANTAINE (hypothèse : canal caché).

Leçon mesurée : une première politique « plateaux → SIGNALER » envoyait les ondes
carrées étrangères en « capteur défaillant ». C'est le piège du §4.3 qui réapparaît
au niveau de l'agent ; la décision de BOB doit primer sur l'indice de plateau.
"""

from omega_hermes.alice import ARTIFACT, LABELS, UNKNOWN
from omega_hermes.commun import Banc
from omega_hermes.twin import CLASSES

ATTENDU = {**{c: "ACCEPTER" for c in CLASSES}, ARTIFACT: "SIGNALER",
           **{l: "QUARANTAINE" for l in LABELS if l not in CLASSES and l != ARTIFACT}}


def decider(decision: str, plateau: bool, distance: float, seuil: float) -> tuple[str, str]:
    if Banc.accepte(decision):
        return "ACCEPTER", f"régime {decision} reconnu (distance {distance:.1f} < seuil strict {seuil:.1f})"
    if decision == UNKNOWN:
        return "QUARANTAINE", (f"au-delà du seuil lâche (distance {distance:.1f}) : source étrangère, "
                               "à isoler même si le signal a des plateaux")
    if plateau:
        return "SIGNALER", "plateaux exacts : capteur défaillant probable (écrêtage ou décrochage)"
    return "QUARANTAINE", (f"rejet sans plateau (distance {distance:.1f}) : source étrangère "
                           "ou canal caché, à isoler")


def simuler(banc: Banc, journal=None, *, agents=4, observations=30) -> dict:
    lignes = []
    for a in range(agents):
        X, labels, familles = banc.alice.lot(observations)
        decisions, dmin, _, plat = banc.juger(X)
        for lab, fam, d, dist, p in zip(labels, familles, decisions, dmin, plat):
            action, hypothese = decider(d, bool(p), float(dist), banc.bob.seuil_strict)
            ok = action == ATTENDU[lab]
            lignes.append({"agent": f"agent-{a + 1}", "label": lab, "famille": fam, "action": action,
                           "attendu": ATTENDU[lab], "ok": ok})
            if journal is not None:
                journal.inscrire("agent", action, "hypothese_explicite",
                                 {"agent": f"agent-{a + 1}", "hypothese": hypothese, "bob": d})
    erreurs = [l for l in lignes if not l["ok"]]
    return {"agents": agents, "decisions": len(lignes),
            "exactitude": 1 - len(erreurs) / len(lignes),
            "par_action": {act: sum(l["action"] == act for l in lignes)
                           for act in ("ACCEPTER", "SIGNALER", "QUARANTAINE")},
            "anomalies_acceptees": sum(l["action"] == "ACCEPTER" and l["attendu"] != "ACCEPTER" for l in lignes),
            "erreurs": erreurs}
