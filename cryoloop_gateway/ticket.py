"""Outil du propriétaire : signe un ticket pour la passerelle (côté émetteur).

  python3 -m cryoloop_gateway.ticket --cle-privee ~/coffre/passerelle.cle --action inscrire
"""

import argparse
import json
import os
import sys
import time

from cryoloop_gateway.gateway import signer_ticket


def fabriquer(graine: bytes, action: str, parametres=None, *, duree_s=300, maintenant=None) -> dict:
    t = int(time.time() if maintenant is None else maintenant)
    return signer_ticket(graine, {"id": os.urandom(16).hex(), "emis": t, "expire": t + duree_s,
                                  "action": action, "parametres": parametres or {}})


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python3 -m cryoloop_gateway.ticket")
    ap.add_argument("--cle-privee", required=True)
    ap.add_argument("--action", required=True)
    ap.add_argument("--duree", type=int, default=300)
    a = ap.parse_args(argv)
    with open(a.cle_privee, "rb") as fh:
        print(json.dumps(fabriquer(fh.read(), a.action, duree_s=a.duree)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
