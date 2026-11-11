"""Vérification de la phase 0 (blueprint §12) : arborescence et conventions.

Sort en 0 si tout est conforme, 1 sinon, et écrit outils/phase0_evidence.json.
"""

import os
import re
import subprocess
import sys

from outils.evidence import ETIQUETTES, ecrire

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FICHIERS = ["VERSION", "CHANGELOG.md", "SECURITY.md", "README.md",
            "master-blueprint-omega-hermes.md", "docs/GABARIT_README_MODULE.md",
            "outils/evidence.py", "outils/changelog.py"]
DOSSIERS = ["omega_hermes", "plateforme_omega", "agent_guard", "cryoloop_gateway",
            "terminal_auth", "rag_wiki", "registre_invariants"]
SECTIONS_GABARIT = ["## Rôle", "## Usage", "## Tests", "## Limites honnêtes"]
BROUILLONS = re.compile(r"(\.tmp|\.bak|\.orig|~|\.swp)$|(^|/)(build|dist)/")


def controles() -> list[tuple[str, bool, str]]:
    res = []
    for f in FICHIERS:
        res.append((f"fichier {f}", os.path.isfile(os.path.join(RACINE, f)), ""))
    for d in DOSSIERS:
        readme = os.path.join(RACINE, d, "README.md")
        ok = os.path.isfile(readme)
        etiq = ""
        if ok:
            with open(readme, encoding="utf-8") as fh:
                m = re.search(r"`\[([^\]]+)\]`", fh.readline())
            etiq = m.group(1) if m else ""
            ok = etiq in ETIQUETTES
        res.append((f"dossier {d}/ avec README étiqueté", ok, etiq))

    with open(os.path.join(RACINE, "VERSION"), encoding="utf-8") as fh:
        version = fh.read().strip()
    res.append(("VERSION au format semver", bool(re.fullmatch(r"\d+\.\d+\.\d+", version)), version))

    with open(os.path.join(RACINE, "docs/GABARIT_README_MODULE.md"), encoding="utf-8") as fh:
        gabarit = fh.read()
    manquantes = [s for s in SECTIONS_GABARIT if s not in gabarit]
    res.append(("gabarit : rôle, usage, tests, limites", not manquantes, ", ".join(manquantes)))

    with open(os.path.join(RACINE, ".gitignore"), encoding="utf-8") as fh:
        ignores = fh.read().split()
    res.append((".src/ ignoré par git", ".src/" in ignores, ""))

    suivis = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard"],
                            cwd=RACINE, capture_output=True, text=True, timeout=10).stdout.split()
    brouillons = [f for f in suivis if BROUILLONS.search(f)]
    res.append(("aucun brouillon de build hors .src/", not brouillons, ", ".join(brouillons)))

    with open(os.path.join(RACINE, "README.md"), encoding="utf-8") as fh:
        readme = fh.read()
    res.append(("README : mission marquée « en attente de confirmation »",
                "en attente de confirmation" in readme, ""))
    res.append(("README : compatibilité déclarée", "### Compatibilité" in readme, ""))
    return res


def main() -> int:
    res = controles()
    for nom, ok, detail in res:
        print(f"[{'OK' if ok else 'ÉCHEC'}] {nom}" + (f" — {detail}" if detail else ""))
    reussis = sum(ok for _, ok, _ in res)
    verdict = "OK" if reussis == len(res) else "ECHEC"
    print(f"\n{reussis}/{len(res)} contrôles — {'TOUT EST OK' if verdict == 'OK' else 'ÉCHEC'}")
    ecrire(os.path.join(RACINE, "outils", "phase0_evidence.json"),
           module="squelette", phase=0, etiquette="VÉRIFIÉ", verdict=verdict,
           config={"fichiers": FICHIERS, "dossiers": DOSSIERS},
           mesures={"controles": len(res), "reussis": reussis,
                    "echecs": [n for n, ok, _ in res if not ok]},
           limites=["Vérifie la présence et la forme, pas le contenu des documents.",
                    "Les dossiers des phases 2 à 7 ne contiennent qu'un README [SPÉCIFIÉ]."])
    return 0 if verdict == "OK" else 1


if __name__ == "__main__":
    sys.exit(main())
