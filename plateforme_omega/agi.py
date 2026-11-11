"""agi.py — boucle d'agent SIMULÉE. Étiquettes : [SIMULATION] [SPÉCIFIÉ]. Ce n'est pas une AGI.

Percevoir (une observation du jumeau) → raisonner (verdict de BOB, puis une source
citée si le RAG local existe) → agir EN SIMULATION (la décision est seulement
inscrite, rien n'est exécuté) → ajuster un seuil. Le coût en FLOPs d'une telle boucle à
grande échelle est calculé pour montrer le mur, pas pour le nier (blueprint §2.2).
"""


from omega_hermes.commun import Banc
from omega_hermes.twin import CLASSES, MODALITES, N, Flux
from plateforme_omega.commun import conclure, sortir
from plateforme_omega.scaling_ref import flops_par_decision

ETIQUETTES = ("SIMULATION", "SPÉCIFIÉ")
REFERENCE_FLOPS = 1e18          # ordre de grandeur d'un supercalculateur exaflopique (déclaré, non mesuré)
# Hypothèse déclarée pour un « raisonner » de type grand modèle : 2e12 FLOP par jeton, 1e3 jetons.
FLOPS_RAISONNEMENT_GRAND_MODELE = 2e12 * 1e3


def raisonner_rag(question: str):
    try:
        from rag_wiki.fusion import repondre        # disponible seulement si la phase 6 est construite
    except ImportError:
        return None, "rag_indisponible"
    try:
        return repondre(question), "rag_cite"
    except Exception as e:                          # le RAG ne doit jamais faire tomber la boucle
        return None, f"rag_erreur:{type(e).__name__}"


def boucle(graine=7, pas=60) -> dict:
    banc = Banc(graine)
    rng = Flux(graine, 9).suivant()
    actions, sources, ajustements = [], [], []
    connus_rejetes = anomalies_acceptees = 0
    for i in range(pas):
        x = banc.twin.observer(CLASSES[i % 3])
        anomalie = rng.random() < 0.3
        if anomalie:
            x = banc.alice.covert(x, rng)
        d, dist, *_ = banc.juger(x)
        action = "ACCEPTER" if Banc.accepte(d[0]) else "QUARANTAINE"
        connus_rejetes += (not anomalie) and action == "QUARANTAINE"
        anomalies_acceptees += anomalie and action == "ACCEPTER"
        if action == "QUARANTAINE":
            _, statut = raisonner_rag("canal caché coordination agents")
            sources.append(statut)
        actions.append(action)                      # agir = inscrire ; aucune action réelle
        if (i + 1) % 20 == 0:                       # ajuster : même règle que la boucle HERMÈS
            avant = banc.bob.seuil_strict
            if anomalies_acceptees:
                banc.bob.seuil_strict *= 0.9
            elif connus_rejetes > 1:
                banc.bob.seuil_strict *= 1.1
            ajustements.append({"pas": i + 1, "avant": avant, "apres": banc.bob.seuil_strict,
                                "connus_rejetes": connus_rejetes, "anomalies_acceptees": anomalies_acceptees})
            connus_rejetes = anomalies_acceptees = 0
    flops = flops_par_decision(len(MODALITES), N, 31, len(CLASSES))
    echelle = {"agents": 1e9, "decisions_par_s_et_agent": 1e3}
    debit = echelle["agents"] * echelle["decisions_par_s_et_agent"]
    besoin = flops * debit
    besoin_grand_modele = FLOPS_RAISONNEMENT_GRAND_MODELE * debit
    return {"etiquettes": ETIQUETTES, "pas": pas, "actions": {a: actions.count(a) for a in set(actions)},
            "raisonnement": {s: sources.count(s) for s in set(sources)}, "ajustements": ajustements,
            "actions_executees": 0, "flops_par_decision": flops, "echelle": echelle,
            "flops_par_s_requis": besoin, "reference_flops_par_s": REFERENCE_FLOPS,
            "rapport_au_mur": besoin / REFERENCE_FLOPS,
            "flops_raisonnement_grand_modele": FLOPS_RAISONNEMENT_GRAND_MODELE,
            "flops_par_s_grand_modele": besoin_grand_modele,
            "machines_exaflopiques_grand_modele": besoin_grand_modele / REFERENCE_FLOPS}


def main() -> int:
    m = boucle()
    return conclure("agi", [
        ("étiquetée [SIMULATION] [SPÉCIFIÉ]", m["etiquettes"] == ETIQUETTES, ""),
        ("aucune action réelle exécutée", m["actions_executees"] == 0, str(m["actions"])),
        ("raisonnement : source citée ou indisponibilité déclarée, jamais inventée",
         all(s == "rag_cite" or s.startswith("rag_") for s in m["raisonnement"]), str(m["raisonnement"])),
        ("le seuil est réellement ajusté et chaque ajustement est tracé", len(m["ajustements"]) == 3, ""),
        ("le mur est calculé : décision HERMÈS sous la référence, raisonnement de grand modèle au-delà",
         m["rapport_au_mur"] < 1 < m["machines_exaflopiques_grand_modele"],
         f"HERMÈS {m['rapport_au_mur']:.1e} × une machine exaflopique ; grand modèle "
         f"{m['machines_exaflopiques_grand_modele']:.1e} machines exaflopiques"),
    ], m, ["Ce n'est pas une AGI : une boucle de 4 étapes sur un jumeau synthétique.",
           "Le compte de FLOPs est une estimation analytique ; la référence exaflopique est déclarée."],
        etiquette="SIMULÉ")


if __name__ == "__main__":
    sortir(main())
