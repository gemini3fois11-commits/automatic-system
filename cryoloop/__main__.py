"""CLI CRYOLOOP Ω∞.

  python3 -m cryoloop valider ARCHIVE [--gamma Γ.jsonl] [--cle-publique HEX] [--journal J.jsonl]
                                      [--sortie DOSSIER] [--repeter N] [périmètre…]
  python3 -m cryoloop banc [--evidence FICHIER]

Codes de sortie de `valider` : 0 ACCEPT (candidat écrit, Γ non committé) · 5 PENDING ·
6 QUARANTINE · 7 REJECT · 2 usage.
"""

import argparse
import json
import os
import sys

from cryoloop.validateur import ETAPES, Perimetre, candidat, valider
from socle_preuve.gamma import Chaine, lire_blocs

SORTIE = {"ACCEPT": 0, "PENDING": 5, "QUARANTINE": 6, "REJECT": 7}
CONSEQUENCE = {"ACCEPT": "candidat Γ produit — commit Γ non effectué (CL-I5)",
               "PENDING": "Γ préservé (CL-I2)",
               "QUARANTINE": "preuves isolées, Γ préservé",
               "REJECT": "candidat rejeté, Γ préservé"}
RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _numero_boucle(journal) -> int:
    if not journal or not os.path.exists(journal):
        return 1
    blocs, _ = lire_blocs(journal)
    return 1 + sum(b["type"] == "cycle" for b in blocs)


def afficher(r, numero, perimetre):
    print(f"CRYOLOOP Ω∞ — LOOP {numero:03d} — {perimetre.nom} · S{perimetre.debut}–S{perimetre.fin}")
    for etape in ETAPES:
        print(f"  {etape:.<28} {r.statut(etape)}")
    for res in r.resolutions:
        print(f"  ↳ {res}")
    for c in r.constats:
        print(f"  • {c.code} [{c.decision}] {c.fichier or ''} {c.detail}".rstrip())
    if r.isolees:
        print(f"  preuves isolées : {len(r.isolees)} — " +
              ", ".join(f"{k} ({v})" for k, v in sorted(r.isolees.items())))
    print(f"DÉCISION : {r.decision} ({r.code_principal}) — {CONSEQUENCE[r.decision]}"
          + ("" if r.gamma_preserve else " — ATTENTION : Γ a changé pendant le cycle"))


def cmd_valider(a) -> int:
    perimetre = Perimetre(a.perimetre, a.debut, a.fin, a.evenements, a.dimension_ekf)
    try:
        cle = bytes.fromhex(a.cle_publique) if a.cle_publique else None
    except ValueError:
        print("erreur : clé publique invalide", file=sys.stderr)
        return 2
    code = 0
    for _ in range(a.repeter):
        numero = _numero_boucle(a.journal)
        r = valider(a.archive, gamma=a.gamma, perimetre=perimetre, cle_publique=cle)
        afficher(r, numero, perimetre)
        if a.journal:
            Chaine(a.journal).inscrire("cycle", r.decision, r.code_principal, {
                "boucle": numero, "perimetre": perimetre.nom, "archive_sha256": r.archive_sha256,
                "codes": r.codes, "base": r.base, "attendu": r.attendu,
                "gamma_preserve": r.gamma_preserve, "isolees": len(r.isolees)})
        if r.decision == "ACCEPT" and a.sortie:
            os.makedirs(a.sortie, exist_ok=True)
            chemin = os.path.join(a.sortie, f"candidat-LOOP-{numero:03d}.json")
            with open(chemin, "w", encoding="utf-8") as fh:
                json.dump(candidat(r, perimetre), fh, ensure_ascii=False, indent=2)
            print(f"  candidat : {chemin}")
        code = SORTIE[r.decision]
    return code


def cmd_banc(a) -> int:
    from cryoloop.preuve import executer
    return executer(a.evidence)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python3 -m cryoloop")
    sub = ap.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("valider", help="un cycle /LOOP sur une archive")
    v.add_argument("archive")
    v.add_argument("--gamma", help="registre canonique Γ (chaîne socle_preuve), lu seulement")
    v.add_argument("--cle-publique", help="clé Ed25519 épinglée qui signe MANIFEST.json")
    v.add_argument("--journal", help="chaîne Γ des décisions de cycle")
    v.add_argument("--sortie", help="dossier où écrire le candidat d'un ACCEPT")
    v.add_argument("--repeter", type=int, default=1)
    d = Perimetre()
    v.add_argument("--perimetre", default=d.nom)
    v.add_argument("--debut", type=int, default=d.debut)
    v.add_argument("--fin", type=int, default=d.fin)
    v.add_argument("--evenements", type=int, default=d.evenements)
    v.add_argument("--dimension-ekf", type=int, default=d.dimension_ekf)
    v.set_defaults(f=cmd_valider)
    b = sub.add_parser("banc", help="matrice de scénarios synthétiques + LOOP 001, écrit l'évidence")
    b.add_argument("--evidence", default=os.path.join(os.path.dirname(__file__),
                                                      "cryoloop_evidence.json"))
    b.set_defaults(f=cmd_banc)
    try:
        a = ap.parse_args(argv)
    except SystemExit as e:
        return 2 if e.code else 0
    return a.f(a)


if __name__ == "__main__":
    sys.exit(main())
