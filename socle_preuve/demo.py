"""Démonstration rejouable du socle de preuve (blueprint §12, phase 1).

Chaque scénario est joué par le vrai CLI dans un sous-processus : les codes de
sortie rapportés sont ceux d'une exécution réelle, pas des valeurs attendues.
"""

import json
import os
import random
import statistics
import subprocess
import sys
import tempfile
import time

from outils.evidence import GRAINE, ecrire
from socle_preuve import ed25519
from socle_preuve.gamma import Chaine, calculer_hash
from socle_preuve.temoin import ScelleurEd25519, ScelleurHMAC, Temoin
from socle_preuve.vecteurs_rfc8032 import verifier_vecteurs

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
N_BLOCS = 12
DECISIONS = [("requete", "REFUS", "hote_non_autorise"),
             ("requete", "REFUS", "tls_non_inspecte"),
             ("requete", "AUTORISE", "allowlist"),
             ("signal", "QUARANTAINE", "inconnu"),
             ("signal", "SIGNALER", "haute_entropie")]


def _cli(*args) -> tuple[int, str]:
    r = subprocess.run([sys.executable, "-m", "socle_preuve", *args], cwd=RACINE,
                       capture_output=True, text=True, timeout=60)
    return r.returncode, (r.stdout + r.stderr).strip()


def _lire(chemin):
    with open(chemin, encoding="utf-8") as fh:
        return [json.loads(l) for l in fh if l.strip()]


def _ecrire(chemin, blocs):
    with open(chemin, "w", encoding="utf-8") as fh:
        for b in blocs:
            fh.write(json.dumps(b, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n")


def _construire(dossier, scelleur, rng):
    journal, temoin = os.path.join(dossier, "gamma.jsonl"), os.path.join(dossier, "temoin.jsonl")
    ch = Chaine(journal, temoin=Temoin(temoin, scelleur))
    for i in range(N_BLOCS):
        t, dec, raison = rng.choice(DECISIONS)
        ch.inscrire(t, dec, raison, {"i": i})
    return journal, temoin


def _reecrire_avec_recalcul(journal, k):
    blocs = _lire(journal)
    blocs[k]["decision"], blocs[k]["raison"] = "AUTORISE", "allowlist"
    prev = blocs[k]["prev_hash"]
    for b in blocs[k:]:
        b["prev_hash"] = prev
        b["hash"] = calculer_hash(b)
        prev = b["hash"]
    _ecrire(journal, blocs)


def _mediane_ms(f, n):
    mesures = []
    for _ in range(n):
        t0 = time.perf_counter_ns()
        f()
        mesures.append(time.perf_counter_ns() - t0)
    return statistics.median(mesures) / 1e6


def executer(chemin_evidence) -> int:
    rng = random.Random(GRAINE)
    k = rng.randrange(2, N_BLOCS - 3)  # bloc visé par les falsifications
    scenarios = []

    def jouer(nom, attendu, code, sortie):
        ok = code == attendu
        scenarios.append({"scenario": nom, "exit_attendu": attendu, "exit_obtenu": code,
                          "sortie": sortie, "ok": ok})
        print(f"[{'OK' if ok else 'ÉCHEC'}] {nom}\n      exit {code} — {sortie}")

    with tempfile.TemporaryDirectory() as tmp:
        secret = os.path.join(tmp, "temoin.secret")
        assert _cli("keygen-hmac", secret)[0] == 0
        with open(secret, "rb") as fh:
            hmac_ = ScelleurHMAC(fh.read())

        # 1. Intact
        d = os.path.join(tmp, "intact"); os.mkdir(d)
        j, t = _construire(d, hmac_, random.Random(GRAINE))
        jouer("chaîne intacte, vérification locale", 0, *_cli("verifier", j))
        jouer("chaîne intacte, témoin HMAC", 0, *_cli("verifier", j, "--temoin", t, "--secret", secret))

        # 2. Falsification simple : un champ modifié, rien recalculé
        d = os.path.join(tmp, "simple"); os.mkdir(d)
        j, t = _construire(d, hmac_, random.Random(GRAINE))
        blocs = _lire(j); blocs[k]["raison"] = "allowlist"; _ecrire(j, blocs)
        jouer(f"falsification simple du bloc {k}", 3, *_cli("verifier", j))

        # 3. Réécriture avec recalcul : passe l'audit local, pas le témoin
        d = os.path.join(tmp, "recalcul"); os.mkdir(d)
        j, t = _construire(d, hmac_, random.Random(GRAINE))
        _reecrire_avec_recalcul(j, k)
        jouer(f"réécriture du bloc {k} avec recalcul, vérification locale seule", 0, *_cli("verifier", j))
        jouer(f"réécriture du bloc {k} avec recalcul, témoin HMAC", 4,
              *_cli("verifier", j, "--temoin", t, "--secret", secret))

        # 4. L'attaquant refait aussi les sceaux, mais sans le vrai secret
        faux = ScelleurHMAC(os.urandom(32))
        os.remove(t)
        tf = Temoin(t, faux)
        for b in _lire(j):
            tf.attester(b)
        jouer("réécriture + sceaux refaits avec un faux secret", 4,
              *_cli("verifier", j, "--temoin", t, "--secret", secret))

        # 5. Troncature du journal seul
        d = os.path.join(tmp, "troncature"); os.mkdir(d)
        j, t = _construire(d, hmac_, random.Random(GRAINE))
        _ecrire(j, _lire(j)[:-2])
        jouer("journal tronqué de 2 blocs", 4, *_cli("verifier", j, "--temoin", t, "--secret", secret))

        # 6. Témoin Ed25519 : le vérificateur n'a que la clé publique épinglée
        cle = os.path.join(tmp, "temoin.cle")
        code, sortie = _cli("keygen-ed25519", cle)
        publique = sortie.rsplit(" ", 1)[-1]
        with open(cle, "rb") as fh:
            ed = ScelleurEd25519(fh.read())
        d = os.path.join(tmp, "ed25519"); os.mkdir(d)
        j, t = _construire(d, ed, random.Random(GRAINE))
        jouer("chaîne intacte, témoin Ed25519 (clé publique épinglée)", 0,
              *_cli("verifier", j, "--temoin", t, "--cle-publique", publique))
        _reecrire_avec_recalcul(j, k)
        jouer(f"réécriture du bloc {k} avec recalcul, témoin Ed25519", 4,
              *_cli("verifier", j, "--temoin", t, "--cle-publique", publique))

        # 7. Secret mal protégé : refus
        os.chmod(secret, 0o644)
        jouer("secret HMAC en mode 644", 2, *_cli("verifier", j, "--temoin", t, "--secret", secret))

    vecteurs = verifier_vecteurs()
    print(f"\nRFC 8032 : {sum(ok for *_, ok in vecteurs)}/{len(vecteurs)} contrôles")

    graine = bytes(range(32))
    sig = ed25519.signer(graine, b"x")
    pub = ed25519.cle_publique(graine)
    n = 200
    plancher = _mediane_ms(lambda: None, 10_000)
    signer_ms = _mediane_ms(lambda: ed25519.signer(graine, b"x"), n) - plancher
    verifier_ms = _mediane_ms(lambda: ed25519.verifier(pub, b"x", sig), n) - plancher
    print(f"Ed25519 (médiane sur {n}, plancher {plancher * 1e3:.2f} µs soustrait) : "
          f"signer {signer_ms:.2f} ms, vérifier {verifier_ms:.2f} ms")

    reussis = sum(s["ok"] for s in scenarios)
    vecteurs_ok = all(ok for *_, ok in vecteurs)
    verdict = "OK" if reussis == len(scenarios) and vecteurs_ok else "ECHEC"
    print(f"\n{reussis}/{len(scenarios)} scénarios — "
          f"{'TOUT EST OK' if verdict == 'OK' else 'ÉCHEC'}")
    ecrire(chemin_evidence, module="socle_preuve", phase=1, etiquette="VÉRIFIÉ", verdict=verdict,
           config={"blocs_par_journal": N_BLOCS, "bloc_vise": k,
                   "codes_sortie": {"0": "intègre", "2": "usage", "3": "chaîne rompue",
                                    "4": "témoin en désaccord"}},
           mesures={"scenarios": scenarios, "scenarios_reussis": reussis,
                    "rfc8032": {"controles": len(vecteurs),
                                "reussis": sum(ok for *_, ok in vecteurs),
                                "vecteurs": sorted({v[0] for v in vecteurs})},
                    "ed25519_ms": {"iterations": n, "plancher_ms": plancher,
                                   "signer_mediane": signer_ms, "verifier_mediane": verifier_ms}},
           limites=["Secret du témoin et journal sur la même machine : un attaquant qui la contrôle "
                    "peut réécrire et resceller (§3.2).",
                    "Une troncature cohérente du journal et du fichier témoin n'est pas détectable "
                    "sans ancre de tête externe.",
                    "4 vecteurs RFC 8032 sur 5 : TEST 1024 non transcrit.",
                    "Ed25519 pur Python, pas à temps constant : vérification et démonstration seulement.",
                    "Durées mesurées sur la machine indiquée dans execution.plateforme."])
    return 0 if verdict == "OK" else 1
