"""Outils communs des modules de la plateforme : un module = un main() qui mesure,
affiche ses critères et écrit son évidence."""

import os
import sys

from outils.evidence import GRAINE, ecrire

DOSSIER = os.path.dirname(os.path.abspath(__file__))


def conclure(module: str, criteres: list[tuple[str, bool, str]], mesures: dict, limites: list[str], *,
             etiquette: str = "VÉRIFIÉ", config: dict | None = None, dossier: str = DOSSIER,
             phase: int = 5) -> int:
    for nom, ok, detail in criteres:
        print(f"[{'OK' if ok else 'ÉCHEC'}] {nom}" + (f" — {detail}" if detail else ""))
    reussis = sum(bool(ok) for _, ok, _ in criteres)
    verdict = "OK" if reussis == len(criteres) else "ECHEC"
    print(f"{module} : {reussis}/{len(criteres)} critères — {'TOUT EST OK' if verdict == 'OK' else 'ÉCHEC'}")
    ecrire(os.path.join(dossier, f"{module}_evidence.json"), module=module, phase=phase,
           etiquette=etiquette, verdict=verdict, graine=GRAINE, config=config or {},
           mesures=mesures | {"criteres": [{"critere": n, "ok": bool(ok), "detail": d} for n, ok, d in criteres]},
           limites=limites)
    return 0 if verdict == "OK" else 1


def lignes_de_code(*fichiers) -> int:
    total = 0
    for f in fichiers:
        with open(os.path.join(DOSSIER, f) if not os.path.isabs(f) else f, encoding="utf-8") as fh:
            total += sum(1 for l in fh if l.strip() and not l.strip().startswith("#"))
    return total


def sortir(code: int):
    sys.exit(code)
