"""Phase 4 (blueprint §12) : essaim, rêverie, mode IA, évasion, attrape, brouillons, guardian.

Chaque module écrit son évidence ; la rêverie est rejouée pour prouver qu'elle élit les mêmes rêves.

  python3 -m omega_hermes.phase4
"""

import json
import os
import sys
import tempfile

import numpy as np

from omega_hermes import ai_mode, attrape, brouillons, evasion, guardian, reverie, swarm
from omega_hermes.commun import Banc
from outils.evidence import GRAINE, ecrire
from socle_preuve.gamma import Chaine, lire_blocs

DOSSIER = os.path.dirname(os.path.abspath(__file__))
SIMULE = "Données synthétiques uniquement : rien ici ne prouve quoi que ce soit sur un système réel."


def _guardian(graine: int) -> dict:
    rng = np.random.default_rng(np.random.SeedSequence([graine, 7]))
    profils = {p: [guardian.analyser(guardian.synthetique(rng, p)) for _ in range(30)]
               for p in ("humain", "robot", "injection", "hesitation")}
    attendu = {"robot": "frappe_robotique", "injection": "injection_rafale",
               "hesitation": "effacements_anormaux"}
    refuse = []
    for interdit in ({"categorie": "lettre", "t_appui_ms": 0, "t_relache_ms": 1, "caractere": "a"},
                     {"touche": "KeyA", "t_appui_ms": 0, "t_relache_ms": 1}):
        try:
            guardian.analyser([interdit] * 12)
            refuse.append(False)
        except guardian.EvenementRefuse:
            refuse.append(True)
    return {"faux_positifs_humain": float(np.mean([r["verdict"] != "NORMAL" for r in profils["humain"]])),
            "detection": {p: float(np.mean([s in r["signaux"] for r in profils[p]])) for p, s in attendu.items()},
            "caracteres_refuses_a_l_entree": all(refuse), "flux_par_profil": 30}


MODULES = ("swarm", "reverie", "ai_mode", "evasion", "attrape", "brouillons", "guardian")


def executer(graine: int = GRAINE, dossier: str = DOSSIER, modules=MODULES) -> int:
    banc = Banc(graine)
    resultats = {}
    voulu = set(modules)
    with tempfile.TemporaryDirectory() as tmp:
        if "swarm" in voulu:
            ref = swarm.simuler(banc)
            bal = swarm.balayage(banc)
            resultats["swarm"] = ({"reference": ref, "balayage": bal}, [
                ("tous les nœuds compromis détectés en 0 battement",
                 ref["tous_detectes"] and ref["latence_max_battements"] == 0),
                ("720 messages cachés émis (3 nœuds × 30 battements × 8 impulsions)", ref["messages_caches"] == 720),
                ("ampleur 3/8", ref["ampleur"] == 0.375),
                ("fausses alarmes < 5 %", ref["fausses_alarmes"] < 0.05),
                ("balayage : chaque niveau compromis détecté", all(b["tous_detectes"] for b in bal))])

        if "reverie" in voulu:
            c1, c2 = reverie.cycle(Banc(graine)), reverie.cycle(Banc(graine))
            resultats["reverie"] = ({k: v for k, v in c1.items() if k != "reves"} | {"reves": c1["reves"]}, [
                ("souffle stable (acceptation ≥ 0,9)", c1["respire"]["acceptation"] >= 0.9),
                ("DORT : aucun appel à BOB", c1["dort"]["sans_jugement"]),
                ("CHOISI reproductible : mêmes élus au second cycle", c1["choisi"] == c2["choisi"]),
                ("l'élection n'invente aucune classe : tous les élus sont des rejets",
                 all(not Banc.accepte(e["decision"]) for e in c1["choisi"]))])

        if "ai_mode" in voulu:
            journal_ia = Chaine(os.path.join(tmp, "ia.jsonl"))
            ia = ai_mode.simuler(banc, journal_ia)
            blocs_ia, rapport_ia = lire_blocs(journal_ia.chemin)
            resultats["ai_mode"] = (ia | {"journal_integre": rapport_ia.integre}, [
                ("aucune anomalie acceptée", ia["anomalies_acceptees"] == 0),
                ("exactitude ≥ 0,95", ia["exactitude"] >= 0.95),
                ("chaque décision inscrite avec son hypothèse",
                 rapport_ia.integre and len(blocs_ia) == ia["decisions"]
                 and all(b["donnees"]["hypothese"] for b in blocs_ia))])

        if "evasion" in voulu:
            ev = evasion.grille(banc)
            resultats["evasion"] = (ev, [
                ("960 cas", ev["cas"] == 960),
                ("aucune évasion à l'amplitude de référence 0,8",
                 all(v == 0.0 for v in ev["taux_a_amplitude_reference"].values())),
                ("plancher de détection à 100 % mesuré pour les deux canaux",
                 all(v is not None for v in ev["amplitude_min_detectee_100pct"].values()))])

        if "attrape" in voulu:
            journal_q = Chaine(os.path.join(tmp, "quarantaine.jsonl"))
            at = attrape.pieger(banc, journal_q)
            blocs_q, rapport_q = lire_blocs(journal_q.chemin)
            resultats["attrape"] = (at | {"quarantaines": len(blocs_q), "journal_integre": rapport_q.integre,
                                          "exemple_motif": blocs_q[0]["donnees"] if blocs_q else None}, [
                ("chaque rejet mis en quarantaine", len(blocs_q) == at["rejets"]),
                ("chaque quarantaine motivée (7 champs)",
                 all(set(attrape.CHAMPS_MOTIF) <= set(b["donnees"]) for b in blocs_q)),
                ("journal de quarantaine intègre", rapport_q.integre)])

        if "brouillons" in voulu:
            br = brouillons.isoler(banc)
            resultats["brouillons"] = (br, [
                ("DRAFT rejeté à 100 %", br["DRAFT"]["rejet"] == 1.0),
                ("nominal rejeté < 5 %", br["nominal"]["rejet"] < 0.05),
                ("DRAFT découplé (corrélation médiane < 0,1), COVERT couplé (> 0,1)",
                 br["DRAFT"]["xcorr_mediane"] < 0.1 < br["COVERT"]["xcorr_mediane"])])

        if "guardian" in voulu:
            gu = _guardian(graine)
            texte = json.dumps(gu)
            resultats["guardian"] = (gu, [
                ("caractères refusés à l'entrée", gu["caracteres_refuses_a_l_entree"]),
                ("aucune clé de contenu dans la sortie",
                 not any(k in texte for k in ('"caractere"', '"touche"', '"key"', '"char"'))),
                ("détection robot / injection / hésitation ≥ 90 %", all(v >= 0.9 for v in gu["detection"].values())),
                ("faux positifs sur frappe humaine ≤ 10 %", gu["faux_positifs_humain"] <= 0.1)])

    limites = {
        "swarm": [SIMULE, "Battement de 5 s simulé : aucune horloge réelle, aucun réseau.",
                  "Fausses alarmes mesurées au seuil appris, avant l'ajustement de la boucle."],
        "reverie": [SIMULE, "L'élection ordonne des candidats, elle ne crée pas de classe."],
        "ai_mode": [SIMULE, "Agents simulés ; la politique est écrite à la main, pas apprise."],
        "evasion": [SIMULE, "Le taux global dépend de la grille ; la courbe par amplitude est la mesure utile.",
                    "Attaquant naïf : il baisse l'amplitude, il n'optimise pas contre BOB."],
        "attrape": [SIMULE],
        "brouillons": [SIMULE, "La discrimination DRAFT / COVERT est une règle sur le trait 31, pas un classifieur."],
        "guardian": [SIMULE, "Événements synthétiques déjà abstraits : ce module ne lit aucun clavier.",
                     "Seuils CV 0,05 et vol 15 ms choisis à la main ; effacements : test binomial à 3 σ "
                     "contre un taux humain de base de 5 %, hypothèse déclarée et non mesurée sur des humains.",
                     "Un premier seuil fixe à 35 % ne détectait que 87 % des flux « hésitation » : remplacé "
                     "par le test binomial avant publication."],
    }
    total_ok = True
    for module, (mesures, criteres) in resultats.items():
        ok = all(c for _, c in criteres)
        total_ok &= ok
        print(f"{module:11s} {'OK   ' if ok else 'ÉCHEC'} " + " · ".join(
            f"{'✓' if c else '✗'} {n}" for n, c in criteres))
        ecrire(os.path.join(dossier, f"{module}_evidence.json"), module=module, phase=4, etiquette="SIMULÉ",
               verdict="OK" if ok else "ECHEC", graine=graine, config={"banc": "Banc(graine, 150 par classe)"},
               mesures=mesures | {"criteres": [{"critere": n, "ok": bool(c)} for n, c in criteres]},
               limites=limites[module])
    n = sum(len(c) for _, c in resultats.values())
    reussis = sum(bool(x) for _, c in resultats.values() for _, x in c)
    print(f"\n{reussis}/{n} critères sur {len(resultats)} module(s) — {'TOUT EST OK' if total_ok else 'ÉCHEC'}")
    return 0 if total_ok else 1


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(prog="python3 -m omega_hermes.phase4")
    ap.add_argument("--module", choices=MODULES, action="append")
    a = ap.parse_args()
    sys.exit(executer(modules=a.module or MODULES))
