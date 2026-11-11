"""Vérification statique du découplage monde réel / banc d'essai (blueprint §1.5).

Les modules du banc (twin, alice, eyes, bob, hermes) ne peuvent importer qu'une
liste blanche et n'appellent ni open, ni eval, ni les lecteurs de fichiers de
numpy. Refuser avant de croire : tout import hors liste est une violation.
"""

import ast
import os

DOSSIER = os.path.dirname(os.path.abspath(__file__))
MODULES_BANC = ("twin.py", "alice.py", "eyes.py", "bob.py", "hermes.py")
IMPORTS_AUTORISES = {"numpy", "math", "typing", "dataclasses", "collections", "statistics",
                     "omega_hermes"}
APPELS_INTERDITS = {"open", "eval", "exec", "compile", "__import__", "input", "breakpoint"}
ATTRIBUTS_INTERDITS = {"load", "loadtxt", "fromfile", "genfromtxt", "memmap", "save", "savez",
                       "savetxt", "tofile", "fromregex", "DataSource"}


def violations(chemins=None) -> list[dict]:
    trouvees = []
    for chemin in chemins or [os.path.join(DOSSIER, m) for m in MODULES_BANC]:
        with open(chemin, encoding="utf-8") as fh:
            arbre = ast.parse(fh.read(), chemin)
        nom = os.path.basename(chemin)
        for noeud in ast.walk(arbre):
            motif = None
            if isinstance(noeud, ast.Import):
                hors = [a.name for a in noeud.names if a.name.split(".")[0] not in IMPORTS_AUTORISES]
                motif = f"import {', '.join(hors)}" if hors else None
            elif isinstance(noeud, ast.ImportFrom):
                racine = (noeud.module or "").split(".")[0]
                motif = f"from {noeud.module} import" if racine not in IMPORTS_AUTORISES else None
            elif isinstance(noeud, ast.Call) and isinstance(noeud.func, ast.Name):
                motif = f"appel {noeud.func.id}()" if noeud.func.id in APPELS_INTERDITS else None
            elif isinstance(noeud, ast.Attribute) and noeud.attr in ATTRIBUTS_INTERDITS:
                motif = f"attribut .{noeud.attr}"
            if motif:
                trouvees.append({"fichier": nom, "ligne": noeud.lineno, "motif": motif})
    return sorted(trouvees, key=lambda v: (v["fichier"], v["ligne"]))
