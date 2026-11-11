"""Génère la paire de clés des tickets de la passerelle — à lancer par le propriétaire.

La clé privée est écrite (mode 600, jamais écrasée) à l'emplacement choisi, qui doit
être HORS du dépôt ; seule la clé publique est épinglée dans DOSSIER_ETAT.

  python3 -m cryoloop_gateway.keygen --cle-privee ~/coffre/passerelle.cle
"""

import argparse
import os
import sys

from socle_preuve import ed25519

DOSSIER = os.path.dirname(os.path.abspath(__file__))
RACINE = os.path.dirname(DOSSIER)


def generer(cle_privee: str, etat: str) -> str:
    cible = os.path.realpath(cle_privee)
    if os.path.commonpath([cible, os.path.realpath(RACINE)]) == os.path.realpath(RACINE):
        raise ValueError("la clé privée ne doit pas être écrite dans le dépôt")
    graine = os.urandom(32)
    fd = os.open(cible, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as fh:
        fh.write(graine)
    os.makedirs(etat, mode=0o700, exist_ok=True)
    publique = ed25519.cle_publique(graine).hex()
    with open(os.path.join(etat, "cle_publique.hex"), "w") as fh:
        fh.write(publique + "\n")
    return publique


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python3 -m cryoloop_gateway.keygen")
    ap.add_argument("--cle-privee", required=True)
    ap.add_argument("--etat", default=os.path.join(DOSSIER, "etat"))
    a = ap.parse_args(argv)
    try:
        publique = generer(a.cle_privee, a.etat)
    except (ValueError, FileExistsError) as e:
        print(f"refus : {e}", file=sys.stderr)
        return 2
    print(f"clé privée : {a.cle_privee} (mode 600, à garder hors de cette machine)")
    print(f"clé publique épinglée : {publique}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
