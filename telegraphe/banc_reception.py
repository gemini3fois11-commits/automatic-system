"""Banc du télégraphe qui refuse : six scénarios de réception, verdicts scellés.

Mesure chaque verdict de bout en bout (émission authentifiée → AFSK → démodulation
→ gardien → sceau Γ) et écrit telegraphe/reception_evidence.json.

Usage : python3 -m telegraphe.banc_reception [--graine 7] [--evidence FICHIER]
"""

import argparse
import json
import os
import random
import sys
import tempfile

from outils.evidence import GRAINE, ecrire
from socle_preuve.gamma import calculer_hash, verifier_chaine
from socle_preuve.temoin import ScelleurHMAC, verifier_temoin
from telegraphe import afsk, reception as R


def _horloge(rng):
    s = rng.randrange(10)
    def h():
        nonlocal s
        s += 1
        return f"2026-02-02T00:{s // 60:02d}:{s % 60:02d}.000000Z"
    return h


def mesurer(graine: int = GRAINE) -> dict:
    rng = random.Random(graine)
    ka = bytes(rng.randrange(256) for _ in range(32))
    kb = bytes(rng.randrange(256) for _ in range(32))
    secret = bytes(rng.randrange(256) for _ in range(32))
    with tempfile.TemporaryDirectory() as d:
        j, t = os.path.join(d, "reception.jsonl"), os.path.join(d, "temoin.jsonl")
        g = R.GardienReception({"F5OEG": ka, "OMEGA": kb}, j, t, ScelleurHMAC(secret),
                               horloge=_horloge(rng))

        bon = R.construire_message("F5OEG", 1, "SOS OMEGA HERMES", ka)
        scenarios = []

        def jouer(nom, bits, attendu_decision, attendu_raison, par_signal=False):
            v = (g.recevoir_signal(afsk.moduler(bits), len(bits)) if par_signal
                 else g.recevoir(bits))
            scenarios.append({"scenario": nom, "decision": v.decision, "raison": v.raison,
                              "attendu": [attendu_decision, attendu_raison],
                              "ok": (v.decision, v.raison) == (attendu_decision, attendu_raison)})

        corrompu = list(bon); corrompu[40] ^= 1
        jouer("émetteur connu, authentifié (via AFSK réel)", bon, R.ACCEPTE, "authentifie", par_signal=True)
        jouer("authentification invalide (mauvaise clé)",
              R.construire_message("F5OEG", 2, "faux", b"\x00" * 32), R.QUARANTAINE, "authentification_invalide")
        jouer("émetteur inconnu (hors allowlist)",
              R.construire_message("PIRATE", 3, "coucou", b"\x00" * 32), R.QUARANTAINE, "emetteur_inconnu")
        jouer("rejeu d'un message déjà accepté", bon, R.QUARANTAINE, "rejeu")
        jouer("trame corrompue (CRC rompu)", corrompu, R.REFUSE, "crc_invalide")
        jouer("second émetteur connu, authentifié",
              R.construire_message("OMEGA", 7, "GRAINE 7", kb), R.ACCEPTE, "authentifie")

        sain = verifier_temoin(j, t, ScelleurHMAC(secret))

        # Effacer un refus avec recalcul : audit local trompé, témoin en désaccord.
        with open(j) as fh:
            blocs = [json.loads(l) for l in fh]
        i_quar = next(k for k, b in enumerate(blocs) if b["decision"] == R.QUARANTAINE)
        blocs[i_quar]["decision"] = R.ACCEPTE
        blocs[i_quar]["raison"] = "authentifie"
        prev = blocs[i_quar - 1]["hash"] if i_quar > 0 else "0" * 64
        for b in blocs[i_quar:]:
            b["prev_hash"] = prev
            b["hash"] = calculer_hash(b)
            prev = b["hash"]
        with open(j, "w") as fh:
            for b in blocs:
                fh.write(json.dumps(b, sort_keys=True, separators=(",", ":"),
                                    ensure_ascii=False) + "\n")
        chaine_coherente = verifier_chaine(j).integre
        apres = verifier_temoin(j, t, ScelleurHMAC(secret))

    return {
        "scenarios": scenarios,
        "verdicts": {v: sum(s["decision"] == v for s in scenarios)
                     for v in (R.ACCEPTE, R.QUARANTAINE, R.REFUSE)},
        "sceau": {"blocs": sain.chaine.blocs, "temoin_accord": sain.accord},
        "reecriture": {"chaine_coherente": chaine_coherente,
                       "temoin_detecte": not apres.accord,
                       "seq_fautif": apres.seq_fautif, "raison": apres.raison},
    }


def criteres(m: dict) -> list[tuple[str, bool, str]]:
    s = m["scenarios"]
    quar = [x for x in s if x["decision"] == R.QUARANTAINE]
    return [
        ("chaque scénario rend le verdict attendu", all(x["ok"] for x in s),
         f"{sum(x['ok'] for x in s)}/{len(s)}"),
        ("l'inconnu est mis en quarantaine avec une raison écrite, jamais livré en silence",
         all(x["raison"] for x in quar) and any(x["raison"] == "emetteur_inconnu" for x in quar),
         f"{len(quar)} quarantaine(s) : " + ", ".join(sorted({x['raison'] for x in quar}))),
        ("tout verdict scellé, chaîne intègre et témoin en accord",
         m["sceau"]["temoin_accord"] and m["sceau"]["blocs"] == len(s), f"{m['sceau']['blocs']} blocs"),
        ("réécriture d'un verdict détectée par le témoin",
         m["reecriture"]["chaine_coherente"] and m["reecriture"]["temoin_detecte"],
         f"Γ cohérente, témoin : {m['reecriture']['raison']} seq {m['reecriture']['seq_fautif']}"),
    ]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python3 -m telegraphe.banc_reception")
    ap.add_argument("--graine", type=int, default=GRAINE)
    ap.add_argument("--evidence", default=os.path.join(os.path.dirname(__file__),
                                                       "reception_evidence.json"))
    a = ap.parse_args(argv)

    m = mesurer(a.graine)
    liste = criteres(m)
    print(f"Télégraphe qui refuse — graine {a.graine}")
    for s in m["scenarios"]:
        print(f"  [{'OK' if s['ok'] else 'ÉCHEC'}] {s['scenario']} → {s['decision']} ({s['raison']})")
    for nom, ok, detail in liste:
        print(f"[{'OK' if ok else 'ÉCHEC'}] {nom}" + (f" — {detail}" if detail else ""))
    reussis = sum(ok for _, ok, _ in liste)
    verdict = "OK" if reussis == len(liste) else "ECHEC"
    print(f"\nreception : {reussis}/{len(liste)} critères — "
          f"{'TOUT EST OK' if verdict == 'OK' else 'ÉCHEC'}")

    ecrire(a.evidence, module="reception", phase=7, etiquette="VÉRIFIÉ", verdict=verdict,
           graine=a.graine,
           config={"allowlist": ["F5OEG", "OMEGA"], "auth": "HMAC-SHA256",
                   "verdicts": [R.ACCEPTE, R.QUARANTAINE, R.REFUSE]},
           mesures=m | {"criteres": [{"critere": n, "ok": ok, "detail": d} for n, ok, d in liste]},
           limites=[
               "Le gardien n'authentifie pas le CONTENU d'un émetteur légitime compromis : "
               "une clé volée produit des ACCEPTE valides.",
               "Secret partagé sur la machine : qui tient la machine tient clé et journal (§3.2).",
               "Anti-rejeu par (indicatif, seq) en mémoire : perdu au redémarrage, comme la "
               "quarantaine d'agent de GARDIEN.",
               "Pas d'horloge : la fraîcheur n'est pas jugée (un message authentique ancien, "
               "non rejoué dans cette session, passerait). La fenêtre δ reste à spécifier (§14.3).",
               "C'est un banc : indicatifs et clés synthétiques, pas une station réelle.",
           ])
    return 0 if verdict == "OK" else 1


if __name__ == "__main__":
    sys.exit(main())
