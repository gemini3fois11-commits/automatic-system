"""Format commun des fichiers *_evidence.json (blueprint §9).

Un fichier d'évidence n'est écrit que par l'exécution qui le mesure. Il porte
la graine, la configuration, les mesures, le verdict, l'étiquette d'honnêteté
et les limites, plus de quoi rejouer : commande, version de Python, commit.
"""

import datetime
import json
import os
import platform
import subprocess
import sys
import tempfile

GRAINE = 7
ETIQUETTES = frozenset({
    "DÉMONTRÉ", "VÉRIFIÉ", "SIMULÉ", "SPÉCIFIÉ", "EXPÉRIMENTAL", "FICTION", "NON ÉTABLI",
})
FORMAT = 1


def _commit() -> str | None:
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True,
                             timeout=5, cwd=os.path.dirname(os.path.abspath(__file__)))
        return out.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def ecrire(chemin, *, module: str, phase: int, etiquette: str, verdict: str,
           config: dict, mesures: dict, limites: list[str], graine: int = GRAINE) -> dict:
    """Écrit atomiquement l'évidence et la retourne."""
    if etiquette not in ETIQUETTES:
        raise ValueError(f"étiquette inconnue : {etiquette!r}")
    if verdict not in {"OK", "ECHEC"}:
        raise ValueError(f"verdict inconnu : {verdict!r}")
    if not limites:
        raise ValueError("une évidence sans limite écrite est refusée")
    doc = {
        "format": FORMAT,
        "module": module,
        "phase": phase,
        "etiquette": etiquette,
        "verdict": verdict,
        "graine": graine,
        "config": config,
        "mesures": mesures,
        "limites": limites,
        "execution": {
            "genere_le": datetime.datetime.now(datetime.timezone.utc)
                         .isoformat(timespec="seconds").replace("+00:00", "Z"),
            "commande": " ".join([os.path.basename(sys.executable)] + sys.argv),
            "python": platform.python_version(),
            "plateforme": platform.platform(),
            "commit": _commit(),
        },
    }
    chemin = os.fspath(chemin)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(os.path.abspath(chemin)), suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=2, sort_keys=False)
        fh.write("\n")
    os.chmod(tmp, 0o644)
    os.replace(tmp, chemin)
    return doc


def lire(chemin) -> dict:
    with open(chemin, encoding="utf-8") as fh:
        doc = json.load(fh)
    manquants = {"format", "module", "phase", "etiquette", "verdict", "graine",
                 "config", "mesures", "limites", "execution"} - doc.keys()
    if manquants:
        raise ValueError(f"{chemin} : champs manquants {sorted(manquants)}")
    return doc
