"""CLI du socle de preuve.

  python3 -m socle_preuve verifier JOURNAL [--temoin FICHIER (--secret FICHIER | --cle-publique HEX)]
  python3 -m socle_preuve keygen-hmac FICHIER
  python3 -m socle_preuve keygen-ed25519 FICHIER
  python3 -m socle_preuve demo [--evidence FICHIER]

Codes de sortie :
  0  chaîne intègre (et témoin en accord s'il est fourni)
  2  usage invalide, fichier absent ou secret mal protégé
  3  chaîne rompue — le seq fautif est nommé
  4  chaîne localement cohérente mais témoin en désaccord — réécriture détectée
"""

import argparse
import os
import stat
import sys

from socle_preuve.gamma import verifier_chaine
from socle_preuve.temoin import ScelleurHMAC, VerificateurEd25519, verifier_temoin
from socle_preuve import ed25519

OK, USAGE, ROMPUE, DESACCORD = 0, 2, 3, 4


class ErreurUsage(Exception):
    pass


def lire_secret(chemin) -> bytes:
    try:
        st = os.stat(chemin)
    except FileNotFoundError:
        raise ErreurUsage(f"secret introuvable : {chemin}")
    if st.st_mode & 0o077:
        raise ErreurUsage(f"secret_permissions : {chemin} doit être en mode 600 "
                          f"(actuel {stat.S_IMODE(st.st_mode):o})")
    with open(chemin, "rb") as fh:
        return fh.read()


def ecrire_secret(chemin, contenu: bytes) -> None:
    try:
        fd = os.open(chemin, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        raise ErreurUsage(f"refus d'écraser un secret existant : {chemin}")
    with os.fdopen(fd, "wb") as fh:
        fh.write(contenu)


def cmd_verifier(a) -> int:
    if not os.path.isfile(a.journal):
        raise ErreurUsage(f"journal introuvable : {a.journal}")
    if a.temoin is None:
        if a.secret or a.cle_publique:
            raise ErreurUsage("--secret et --cle-publique exigent --temoin")
        r = verifier_chaine(a.journal)
        print(r)
        return OK if r.integre else ROMPUE
    if bool(a.secret) == bool(a.cle_publique):
        raise ErreurUsage("--temoin exige exactement un de --secret ou --cle-publique")
    if not os.path.isfile(a.temoin):
        raise ErreurUsage(f"fichier témoin introuvable : {a.temoin}")
    if a.secret:
        verif = ScelleurHMAC(lire_secret(a.secret))
    else:
        try:
            verif = VerificateurEd25519(bytes.fromhex(a.cle_publique))
        except ValueError as e:
            raise ErreurUsage(f"clé publique invalide : {e}")
    r = verifier_temoin(a.journal, a.temoin, verif)
    print(r)
    if not r.chaine.integre:
        return ROMPUE
    return OK if r.accord else DESACCORD


def cmd_keygen_hmac(a) -> int:
    ecrire_secret(a.fichier, os.urandom(32))
    print(f"secret HMAC créé : {a.fichier} (mode 600). Ne jamais le committer ni le coller.")
    return OK


def cmd_keygen_ed25519(a) -> int:
    graine = os.urandom(32)
    ecrire_secret(a.fichier, graine)
    print(f"clé privée créée : {a.fichier} (mode 600)")
    print(f"clé publique à épingler : {ed25519.cle_publique(graine).hex()}")
    return OK


def cmd_demo(a) -> int:
    from socle_preuve.demo import executer
    return executer(a.evidence)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python3 -m socle_preuve",
                                 description="Socle de preuve : chaîne Γ et témoin.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("verifier", help="vérifie une chaîne Γ, et son témoin si fourni")
    v.add_argument("journal")
    v.add_argument("--temoin")
    v.add_argument("--secret", help="fichier du secret HMAC (mode 600)")
    v.add_argument("--cle-publique", help="clé publique Ed25519 épinglée, en hexadécimal")
    v.set_defaults(f=cmd_verifier)
    k = sub.add_parser("keygen-hmac")
    k.add_argument("fichier")
    k.set_defaults(f=cmd_keygen_hmac)
    k = sub.add_parser("keygen-ed25519")
    k.add_argument("fichier")
    k.set_defaults(f=cmd_keygen_ed25519)
    d = sub.add_parser("demo", help="démonstration rejouable du témoin, écrit l'évidence")
    d.add_argument("--evidence", default=os.path.join(os.path.dirname(__file__),
                                                      "preuve_evidence.json"))
    d.set_defaults(f=cmd_demo)
    try:
        a = ap.parse_args(argv)
    except SystemExit as e:
        return USAGE if e.code else OK
    try:
        return a.f(a)
    except ErreurUsage as e:
        print(f"erreur : {e}", file=sys.stderr)
        return USAGE


if __name__ == "__main__":
    sys.exit(main())
