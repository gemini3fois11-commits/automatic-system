"""Génère CHANGELOG.md depuis VERSION et les fichiers *_evidence.json (blueprint §9.1).

Usage : python3 -m outils.changelog [--verifier]
--verifier : sort en 1 si CHANGELOG.md diffère de ce que produiraient les évidences.
"""

import glob
import os
import sys

from outils.evidence import lire

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXCLUS = {".git", ".src", "__pycache__"}


def evidences() -> list[dict]:
    docs = []
    for chemin in sorted(glob.glob(os.path.join(RACINE, "**", "*_evidence.json"), recursive=True)):
        if EXCLUS & set(os.path.relpath(chemin, RACINE).split(os.sep)):
            continue
        doc = lire(chemin)
        doc["_chemin"] = os.path.relpath(chemin, RACINE)
        docs.append(doc)
    return docs


def rendre() -> str:
    with open(os.path.join(RACINE, "VERSION"), encoding="utf-8") as fh:
        version = fh.read().strip()
    lignes = [
        "# Changelog",
        "",
        "<!-- Généré par `python3 -m outils.changelog` depuis VERSION et les fichiers",
        "     *_evidence.json. Ne pas éditer à la main (blueprint §9.1). -->",
        "",
        f"## {version} — en cours",
        "",
    ]
    docs = evidences()
    if not docs:
        lignes.append("Aucune évidence produite pour l'instant.")
    for doc in sorted(docs, key=lambda d: (d["phase"], d["module"])):
        lignes.append(
            f"- Phase {doc['phase']} · `{doc['module']}` · **{doc['verdict']}** "
            f"`[{doc['etiquette']}]` · {doc['execution']['genere_le']} · "
            f"[évidence]({doc['_chemin']})"
        )
    return "\n".join(lignes) + "\n"


def main(argv: list[str]) -> int:
    contenu = rendre()
    chemin = os.path.join(RACINE, "CHANGELOG.md")
    if "--verifier" in argv:
        try:
            with open(chemin, encoding="utf-8") as fh:
                actuel = fh.read()
        except FileNotFoundError:
            actuel = ""
        if actuel != contenu:
            print("CHANGELOG.md n'est pas à jour : relancer python3 -m outils.changelog")
            return 1
        print("CHANGELOG.md conforme aux évidences")
        return 0
    with open(chemin, "w", encoding="utf-8") as fh:
        fh.write(contenu)
    print(f"CHANGELOG.md régénéré ({contenu.count('- Phase')} entrée(s))")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
