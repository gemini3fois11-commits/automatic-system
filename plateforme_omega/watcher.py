"""Watcher (blueprint §6.2) : surveillance d'intégrité par sceaux et battements.

Le veilleur scelle les empreintes SHA-256 d'un ensemble de fichiers dans une chaîne Γ et
émet un battement à chaque passage. Une sentinelle indépendante vérifie la fraîcheur du
battement : un veilleur réduit au silence est lui-même une alarme.

Les horloges sont injectées : le module ne dépend pas de la charge de la machine, ce qui
supprime la fausse alarme sous charge parallèle que le blueprint documente (§6.1).
"""

import hashlib
import os
import tempfile
import time

from plateforme_omega.commun import conclure, sortir
from socle_preuve.gamma import Chaine, lire_blocs


def empreintes(dossier) -> dict[str, str]:
    res = {}
    for racine, _, noms in os.walk(dossier):
        for nom in sorted(noms):
            chemin = os.path.join(racine, nom)
            with open(chemin, "rb") as fh:
                res[os.path.relpath(chemin, dossier)] = hashlib.sha256(fh.read()).hexdigest()
    return res


class Veilleur:
    def __init__(self, dossier, journal: Chaine, horloge=time.monotonic):
        self.dossier, self.journal, self.horloge = dossier, journal, horloge
        self.sceau = empreintes(dossier)
        self.dernier_battement = horloge()
        journal.inscrire("sceau", "SCELLE", "etat_initial", {"fichiers": len(self.sceau)})

    def passer(self) -> list[dict]:
        actuel = empreintes(self.dossier)
        alarmes = ([{"fichier": f, "alarme": "fichier_supprime"} for f in self.sceau if f not in actuel]
                   + [{"fichier": f, "alarme": "fichier_ajoute"} for f in actuel if f not in self.sceau]
                   + [{"fichier": f, "alarme": "fichier_modifie"} for f in actuel
                      if f in self.sceau and actuel[f] != self.sceau[f]])
        for a in alarmes:
            self.journal.inscrire("alarme", "ALERTE", a["alarme"], a)
        self.dernier_battement = self.horloge()
        self.journal.inscrire("battement", "VIVANT", "passage", {"alarmes": len(alarmes)})
        return alarmes


class Sentinelle:
    def __init__(self, veilleur: Veilleur, horloge=time.monotonic, intervalle_s=5.0, tolerance=3):
        self.veilleur, self.horloge = veilleur, horloge
        self.limite = intervalle_s * tolerance

    def verifier(self) -> str | None:
        return "veilleur_muet" if self.horloge() - self.veilleur.dernier_battement > self.limite else None


def mesurer() -> dict:
    t = {"v": 0.0}
    horloge = lambda: t["v"]
    res = {}
    with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as j:
        for nom, contenu in (("a.json", b"{}"), ("b.bin", b"\x00" * 64)):
            with open(os.path.join(d, nom), "wb") as fh:
                fh.write(contenu)
        journal = Chaine(os.path.join(j, "veille.jsonl"))
        v = Veilleur(d, journal, horloge)
        s = Sentinelle(v, horloge)
        res["nominal"] = v.passer()
        t["v"] += 5
        res["sentinelle_nominale"] = s.verifier()
        with open(os.path.join(d, "a.json"), "wb") as fh:
            fh.write(b'{"x": 1}')
        os.remove(os.path.join(d, "b.bin"))
        with open(os.path.join(d, "c.sh"), "wb") as fh:
            fh.write(b"#!/bin/sh\n")
        res["altere"] = sorted(a["alarme"] for a in v.passer())
        t["v"] += 16                                     # le veilleur ne passe plus
        res["sentinelle_silence"] = s.verifier()
        blocs, rapport = lire_blocs(journal.chemin)
        res["journal"] = {"integre": rapport.integre, "blocs": rapport.blocs}
    return res


def main() -> int:
    m = mesurer()
    return conclure("watcher", [
        ("état nominal : aucune alarme", m["nominal"] == [] and m["sentinelle_nominale"] is None, ""),
        ("modification, suppression et ajout détectés",
         m["altere"] == ["fichier_ajoute", "fichier_modifie", "fichier_supprime"], str(m["altere"])),
        ("veilleur réduit au silence : la sentinelle alarme", m["sentinelle_silence"] == "veilleur_muet", ""),
        ("alarmes et battements scellés dans une chaîne Γ intègre", m["journal"]["integre"], str(m["journal"])),
    ], m, ["Mono-machine : un attaquant qui contrôle l'hôte peut faire taire veilleur et sentinelle ensemble.",
           "Le premier sceau fait foi : un fichier déjà altéré avant le sceau passe pour sain."])


if __name__ == "__main__":
    sortir(main())
