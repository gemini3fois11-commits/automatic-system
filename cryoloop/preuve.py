"""Évidence CRYOLOOP : matrice de scénarios [SIMULÉ] + état réel de LOOP 001."""

import os

from cryoloop.scenarios import tout_jouer
from cryoloop.validateur import valider
from outils.evidence import ecrire

ARCHIVES_REELLES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "archives", "DON-DC01")

# Statuts déclarés dans le texte reçu (SPEC.md §3), à comparer à ce qui est mesuré ici.
DECLARES = {"Continuité S18–S100": "ACCEPT", "Contradiction S50": "PENDING",
            "Preuves cryptographiques": "PENDING", "Validation EKF": "PENDING"}


def executer(chemin_evidence) -> int:
    resultats = tout_jouer()
    print("Banc CRYOLOOP [SIMULÉ] — archives synthétiques au format cryoloop-archive-v0")
    for r in resultats:
        print(f"[{'OK' if r['ok'] else 'ÉCHEC'}] {r['scenario']:47s} → {r['decision']:<10s} "
              f"{', '.join(r['codes']) or 'invariants_ok'}")
    reel = valider(ARCHIVES_REELLES)
    print(f"\nLOOP 001 sur les archives réelles DON-DC01 : {reel.decision} "
          f"({reel.code_principal}) — {os.path.relpath(ARCHIVES_REELLES)}")
    for etape, declare in DECLARES.items():
        print(f"  {etape:.<30} déclaré {declare:<8} mesuré ici : non établi (archives absentes)")
    reussis = sum(r["ok"] for r in resultats)
    loop_ok = reel.decision == "PENDING" and reel.code_principal == "entrees_absentes"
    verdict = "OK" if reussis == len(resultats) and loop_ok else "ECHEC"
    print(f"\n{reussis}/{len(resultats)} scénarios — {'TOUT EST OK' if verdict == 'OK' else 'ÉCHEC'}"
          " — commit Γ : INTERDIT EN L'ÉTAT ACTUEL")
    ecrire(chemin_evidence, module="cryoloop", phase=5, etiquette="SIMULÉ", verdict=verdict,
           config={"format": "cryoloop-archive-v0", "perimetre": "DON-DC01", "epoques": [18, 100],
                   "evenements": 21, "dimension_ekf": 64,
                   "gravite": "QUARANTINE > REJECT > PENDING > ACCEPT"},
           mesures={"scenarios": resultats, "reussis": reussis,
                    "loop_001_reel": {"archive": os.path.relpath(ARCHIVES_REELLES),
                                      "decision": reel.decision, "code": reel.code_principal,
                                      "commit_gamma": "interdit",
                                      "statuts_declares": DECLARES,
                                      "statuts_mesures": "non établis : archives non fournies"}},
           limites=["Les archives du banc sont synthétiques ; elles exercent le validateur, elles ne "
                    "disent rien des archives DON-DC01 réelles, qui n'ont pas été fournies.",
                    "Le format cryoloop-archive-v0 est une proposition : il devra être confronté aux "
                    "vrais EKF_Matrix_State.json et journaux S50–S51.",
                    "La provenance repose sur un manifeste signé Ed25519 par une clé épinglée ; la clé "
                    "du banc est publique par construction.",
                    "Les mesures mémoire / thermique sont contrôlées en présence et en forme, jamais "
                    "interprétées : aucun seuil n'a été inventé.",
                    "P6 (OCC / SQLite WAL) n'est pas couvert ici : Γ est une chaîne JSONL du socle de "
                    "preuve, dont l'OCC est testé dans socle_preuve et rinv."])
    return 0 if verdict == "OK" else 1
