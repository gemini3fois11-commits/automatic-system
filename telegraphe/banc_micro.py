"""Banc de la voie microphone : récepteur AFSK à synchronisation aveugle.

`[EXPÉRIMENTAL]`. Mesure sur une BOUCLE LOCALE dégradée (bruit, décalage, gain,
continu, silences) : récupération exacte, plancher de SNR, et taux de faux
positifs sur bruit pur. Ce banc ne touche aucun micro réel — il n'en existe pas
dans ce conteneur — et ne prétend rien sur un vrai canal acoustique.

Usage : python3 -m telegraphe.banc_micro [--graine 7] [--evidence FICHIER]
"""

import argparse
import os
import random
import sys

from outils.evidence import GRAINE, ecrire
from telegraphe import afsk, micro, trame

MESSAGE = "CQ DE OMEGA HERMES — graine 7.".encode("utf-8")
SNRS = [12, 9, 6, 3, 0, -3]
ESSAIS_PAR_SNR = 30
ESSAIS_BRUIT = 200


def mesurer(graine: int = GRAINE) -> dict:
    rng = random.Random(graine)
    base = afsk.moduler(trame.construire(MESSAGE))
    n = len(base)

    # Dégradation propre (sans bruit) : décalage, continu, gain, silences.
    propre = micro.degrader(base, rng=rng, gain=0.4, continu=0.2,
                            silence_avant=211, silence_apres=133)
    try:
        got, start = micro.recevoir_flux(propre)
        propre_ok = got == MESSAGE
    except trame.TrameInvalide:
        propre_ok, start = False, None

    # Balayage de SNR.
    balayage = []
    for snr in SNRS:
        ok = 0
        for k in range(ESSAIS_PAR_SNR):
            r = random.Random((graine << 8) ^ (snr & 0xFF) << 4 ^ k)
            d = micro.degrader(base, rng=r, snr_db=float(snr), gain=r.uniform(0.3, 1.0),
                               continu=r.uniform(-0.2, 0.2),
                               silence_avant=r.randint(0, 400), silence_apres=r.randint(0, 200))
            try:
                g, _ = micro.recevoir_flux(d)
                ok += g == MESSAGE
            except trame.TrameInvalide:
                pass
        balayage.append({"snr_db": snr, "reussis": ok, "essais": ESSAIS_PAR_SNR})

    # Faux positifs sur bruit pur.
    faux = 0
    for k in range(ESSAIS_BRUIT):
        r = random.Random(0xB00 + k)
        try:
            micro.recevoir_flux([r.gauss(0, 1) for _ in range(n)])
            faux += 1
        except trame.TrameInvalide:
            pass

    plancher_100 = min((b["snr_db"] for b in balayage if b["reussis"] == b["essais"]), default=None)
    return {
        "propre": {"ok": propre_ok, "start": start},
        "balayage_snr": balayage,
        "snr_plancher_100pct_db": plancher_100,
        "faux_positifs": {"essais": ESSAIS_BRUIT, "faux": faux},
        "config_canal": {"mark_hz": afsk.F_MARK, "space_hz": afsk.F_SPACE, "baud": afsk.BAUD,
                         "fs": afsk.FS, "message_octets": len(MESSAGE)},
    }


def criteres(m: dict) -> list[tuple[str, bool, str]]:
    bal = {b["snr_db"]: b for b in m["balayage_snr"]}
    return [
        ("synchro aveugle : récupération exacte à travers décalage/continu/gain/silence",
         m["propre"]["ok"], f"start {m['propre']['start']}"),
        ("aucun faux positif sur bruit pur", m["faux_positifs"]["faux"] == 0,
         f"{m['faux_positifs']['faux']}/{m['faux_positifs']['essais']}"),
        ("récupération fiable à 6 dB (≥ 28/30)", bal[6]["reussis"] >= 28,
         f"{bal[6]['reussis']}/{bal[6]['essais']}"),
        ("récupération fiable à 3 dB (≥ 25/30)", bal[3]["reussis"] >= 25,
         f"{bal[3]['reussis']}/{bal[3]['essais']}"),
        ("plancher 100 % mesuré (déclaré, pas un seuil imposé)",
         m["snr_plancher_100pct_db"] is not None, f"{m['snr_plancher_100pct_db']} dB"),
    ]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python3 -m telegraphe.banc_micro")
    ap.add_argument("--graine", type=int, default=GRAINE)
    ap.add_argument("--evidence", default=os.path.join(os.path.dirname(__file__),
                                                       "micro_evidence.json"))
    a = ap.parse_args(argv)

    m = mesurer(a.graine)
    liste = criteres(m)
    print(f"Voie microphone [EXPÉRIMENTAL] — graine {a.graine}")
    print("  balayage SNR (boucle locale bruitée) :")
    for b in m["balayage_snr"]:
        print(f"    {b['snr_db']:>3} dB : {b['reussis']}/{b['essais']}")
    print(f"  plancher 100 % : {m['snr_plancher_100pct_db']} dB · "
          f"faux positifs : {m['faux_positifs']['faux']}/{m['faux_positifs']['essais']}")
    for nom, ok, detail in liste:
        print(f"[{'OK' if ok else 'ÉCHEC'}] {nom}" + (f" — {detail}" if detail else ""))
    reussis = sum(ok for _, ok, _ in liste)
    verdict = "OK" if reussis == len(liste) else "ECHEC"
    print(f"\nmicro : {reussis}/{len(liste)} critères — "
          f"{'TOUT EST OK' if verdict == 'OK' else 'ÉCHEC'}")

    ecrire(a.evidence, module="micro", phase=7, etiquette="EXPÉRIMENTAL", verdict=verdict,
           graine=a.graine,
           config={"snrs_db": SNRS, "essais_par_snr": ESSAIS_PAR_SNR,
                   "essais_bruit": ESSAIS_BRUIT, "message": MESSAGE.decode("utf-8")},
           mesures=m | {"criteres": [{"critere": n, "ok": ok, "detail": d} for n, ok, d in liste]},
           limites=[
               "[EXPÉRIMENTAL] — vérifié seulement sur une boucle locale dégradée "
               "synthétiquement (bruit blanc, décalage, gain, continu, silences). AUCUN "
               "micro ni canal acoustique réel : les chiffres ne disent rien d'une vraie "
               "transmission par le son (§8.2, « ne jamais la promettre »).",
               "Suppose la fréquence d'échantillonnage et le débit connus : pas de correction "
               "d'écart d'horloge ni de resynchronisation en cours de trame.",
               "Décode une trame unique ; pas de démultiplexage d'un flux continu.",
               "Le bruit est gaussien blanc : ni multitrajet, ni évanouissement, ni "
               "intermodulation d'un vrai canal.",
               "La capture (micro → échantillons) est laissée à l'appelant ; aucune "
               "dépendance audio n'est imposée, donc rien n'est testé de bout en bout depuis "
               "un périphérique.",
           ])
    return 0 if verdict == "OK" else 1


if __name__ == "__main__":
    sys.exit(main())
