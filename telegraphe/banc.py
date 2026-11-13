"""Banc du télégraphe : aller-retour AFSK, Morse adaptatif, émissions scellées.

Mesure tout de bout en bout et écrit telegraphe/telegraphe_evidence.json. Aucun
chiffre n'est tapé à la main (blueprint §9.1) : le README et la console citent
ce fichier.

Usage : python3 -m telegraphe.banc [--graine 7] [--evidence FICHIER]
"""

import argparse
import json
import os
import random
import sys
import tempfile

from outils.evidence import GRAINE, ecrire
from socle_preuve.gamma import calculer_hash, verifier_chaine
from socle_preuve.temoin import ScelleurHMAC
from telegraphe import afsk, morse, registre, trame

MESSAGE_REF = "OMEGA-HERMÈS — le transport se prouve à un témoin. Graine 7."
MOT_MORSE = "CQ DE OMEGA HERMES"
MESSAGES_MORSE = ["OMEGA HERMES", "SOS SOS", "THE QUICK BROWN FOX", "CQ DE F5OEG", "GRAINE 7."]
GIGUE = 0.30
ESSAIS_CORRUPTION = 60


def _afsk_aller_retour(message: str) -> dict:
    octets = message.encode("utf-8")
    bits = trame.construire(octets)
    ech = afsk.moduler(bits)
    recu_mem = trame.analyser(afsk.demoduler(ech, len(bits)))
    ech_wav, fs = afsk.depuis_wav_octets(afsk.vers_wav_octets(ech))
    recu_wav = trame.analyser(afsk.demoduler(ech_wav, len(bits)))
    return {
        "octets": len(octets), "bits": len(bits), "echantillons": len(ech),
        "duree_ms": round(1000 * len(ech) / afsk.FS, 3),
        "crc_x25": f"0x{trame.crc16_x25(octets):04x}",
        "fs": afsk.FS, "mark_hz": afsk.F_MARK, "space_hz": afsk.F_SPACE, "baud": afsk.BAUD,
        "wav_octets": len(afsk.vers_wav_octets(ech)), "fs_wav": fs,
        "exact_memoire": recu_mem == octets, "exact_wav": recu_wav == octets,
    }


def _corruption(message: str, rng: random.Random) -> dict:
    octets = message.encode("utf-8")
    bits = trame.construire(octets)
    base = afsk.moduler(bits)
    rejets = faux = bons = 0
    for _ in range(ESSAIS_CORRUPTION):
        ech = list(base)
        debut = rng.randrange(0, len(ech) - 400)
        for i in range(debut, debut + 400):
            ech[i] = rng.uniform(-1, 1)
        try:
            recu = trame.analyser(afsk.demoduler(ech, len(bits)))
            bons += 1 if recu == octets else 0
            faux += 0 if recu == octets else 1
        except trame.TrameInvalide:
            rejets += 1
    return {"essais": ESSAIS_CORRUPTION, "rejets": rejets, "corrects": bons, "octets_faux_livres": faux}


def _morse(rng: random.Random) -> dict:
    propres = all(morse.depuis_durees(morse.vers_durees(m)) == m.upper() for m in MESSAGES_MORSE)
    ok = total = 0
    for m in MESSAGES_MORSE:
        for unite in (4, 12, 50):
            ev = morse.vers_durees(m, unite=unite)
            marge = int(unite * GIGUE)
            bruite = [(e, max(1, d + rng.randint(-marge, marge))) for e, d in ev]
            total += 1
            ok += morse.depuis_durees(bruite) == m.upper()
    return {"propres_exacts": propres, "gigue_pct": int(GIGUE * 100),
            "gigue_exacts": ok, "gigue_total": total,
            "exemple": {"texte": MOT_MORSE, "code": morse.encoder(MOT_MORSE)}}


def _registre(rng_secret: random.Random) -> dict:
    secret = bytes(rng_secret.randrange(256) for _ in range(32))
    with tempfile.TemporaryDirectory() as d:
        j, t = os.path.join(d, "emissions.jsonl"), os.path.join(d, "temoin.jsonl")
        reg = registre.Registre(j, t, ScelleurHMAC(secret))
        for m in ["SOS", "OMEGA HERMES", "GRAINE 7."]:
            reg.emettre(m)
        sain = registre.verifier(j, t, ScelleurHMAC(secret))

        with open(j) as fh:
            blocs = [json.loads(l) for l in fh]
        blocs[1]["donnees"]["texte"] = "FALSIFIE"
        prev = blocs[0]["hash"]
        for b in blocs[1:]:
            b["prev_hash"] = prev
            b["hash"] = calculer_hash(b)
            prev = b["hash"]
        with open(j, "w") as fh:
            for b in blocs:
                fh.write(json.dumps(b, sort_keys=True, separators=(",", ":"),
                                    ensure_ascii=False) + "\n")
        chaine_coherente = verifier_chaine(j).integre
        apres = registre.verifier(j, t, ScelleurHMAC(secret))
    return {
        "emissions": sain.chaine.blocs,
        "temoin_accord_sain": sain.accord,
        "chaine_coherente_apres_reecriture": chaine_coherente,
        "temoin_detecte_reecriture": not apres.accord,
        "seq_fautif": apres.seq_fautif, "raison": apres.raison,
    }


def mesurer(graine: int = GRAINE) -> dict:
    rng = random.Random(graine)
    return {
        "afsk": _afsk_aller_retour(MESSAGE_REF),
        "corruption": _corruption(MESSAGE_REF, rng),
        "morse": _morse(rng),
        "registre": _registre(rng),
        "crc_valeur_de_controle": {"entree": "123456789", "x25": f"0x{trame.crc16_x25(b'123456789'):04x}"},
    }


def criteres(m: dict) -> list[tuple[str, bool, str]]:
    a, c, mo, r = m["afsk"], m["corruption"], m["morse"], m["registre"]
    return [
        ("aller-retour AFSK exact (mémoire)", a["exact_memoire"],
         f"{a['octets']} o, {a['bits']} bits, {a['echantillons']} éch., {a['duree_ms']:.0f} ms, CRC {a['crc_x25']}"),
        ("aller-retour AFSK exact (WAV)", a["exact_wav"], f"{a['wav_octets']} o WAV à {a['fs_wav']} Hz"),
        ("corruption : aucun octet faux livré", c["octets_faux_livres"] == 0,
         f"{c['octets_faux_livres']} faux sur {c['essais']} essais"),
        ("corruption : détectée au moins une fois", c["rejets"] > 0,
         f"{c['rejets']} rejets, {c['corrects']} corrects"),
        ("Morse aller-retour propre exact", mo["propres_exacts"], ""),
        (f"Morse adaptatif exact sous gigue ±{mo['gigue_pct']} %",
         mo["gigue_exacts"] == mo["gigue_total"], f"{mo['gigue_exacts']}/{mo['gigue_total']}"),
        ("émissions scellées : témoin en accord", r["temoin_accord_sain"], f"{r['emissions']} émissions"),
        ("réécriture recalculée détectée par le témoin",
         r["chaine_coherente_apres_reecriture"] and r["temoin_detecte_reecriture"],
         f"Γ cohérente, témoin : {r['raison']} seq {r['seq_fautif']}"),
        ("CRC-16/X-25 valeur de contrôle 0x906E",
         m["crc_valeur_de_controle"]["x25"] == "0x906e", m["crc_valeur_de_controle"]["x25"]),
    ]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python3 -m telegraphe.banc")
    ap.add_argument("--graine", type=int, default=GRAINE)
    ap.add_argument("--evidence", default=os.path.join(os.path.dirname(__file__),
                                                       "telegraphe_evidence.json"))
    a = ap.parse_args(argv)

    m = mesurer(a.graine)
    liste = criteres(m)
    af = m["afsk"]
    print(f"Télégraphe — graine {a.graine}")
    print(f"  AFSK Bell 202 : mark {af['mark_hz']} Hz / space {af['space_hz']} Hz, "
          f"{af['baud']} bauds, {af['fs']} Hz")
    print(f"  message de référence : {af['octets']} octets → {af['bits']} bits → "
          f"{af['echantillons']} échantillons ({af['duree_ms']:.1f} ms), CRC {af['crc_x25']}")
    for nom, ok, detail in liste:
        print(f"[{'OK' if ok else 'ÉCHEC'}] {nom}" + (f" — {detail}" if detail else ""))
    reussis = sum(ok for _, ok, _ in liste)
    verdict = "OK" if reussis == len(liste) else "ECHEC"
    print(f"\ntélégraphe : {reussis}/{len(liste)} critères — "
          f"{'TOUT EST OK' if verdict == 'OK' else 'ÉCHEC'}")

    ecrire(a.evidence, module="telegraphe", phase=7, etiquette="VÉRIFIÉ", verdict=verdict,
           graine=a.graine,
           config={"mark_hz": afsk.F_MARK, "space_hz": afsk.F_SPACE, "baud": afsk.BAUD,
                   "fs": afsk.FS, "message_reference": MESSAGE_REF,
                   "essais_corruption": ESSAIS_CORRUPTION, "gigue_morse_pct": int(GIGUE * 100)},
           mesures=m | {"criteres": [{"critere": n, "ok": ok, "detail": d} for n, ok, d in liste]},
           limites=[
               "Chiffres mesurés ici à 48 000 Hz ; ce ne sont pas les repères historiques "
               "du blueprint (22 050 Hz, 6 909 échantillons, CRC 0x141e), calculés sur un "
               "autre message et une autre fréquence.",
               "La démodulation aligne ses fenêtres sur le débit connu du flux généré : "
               "aucune récupération d'horloge en aveugle.",
               "Voie microphone : [EXPÉRIMENTAL], non implémentée et jamais promise (§8.2).",
               "Le CRC détecte, il n'authentifie pas : l'authentification est le sceau du "
               "témoin. Un attaquant qui tient la machine tient journal et secret (§3.2).",
               "Le décodeur Morse adaptatif suppose au moins un élément d'une unité (point "
               "ou silence intra) ; un message tout en traits surestime l'unité.",
               "Le « télégraphe qui refuse » (BOB en réception, §8.2) n'est pas implémenté : "
               "il attend la décision du propriétaire.",
           ])
    return 0 if verdict == "OK" else 1


if __name__ == "__main__":
    sys.exit(main())
