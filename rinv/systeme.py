"""Démonstration de bout en bout : un seul système qui prouve ses refus.

    canal volatil (/dev/shm) → trame CRC-16/X-25 → Invariant Gate I₁–I₅
      → registre Γ (transitions acceptées)          ┐ chaînes du socle de preuve,
      → journal Γ des décisions (refus compris)      ┘ scellées par le témoin
    → Void Monitor (quarantaine, purge à 15 s) → Auto-Suture (processus réels)
    → vérification par le témoin, puis tentatives d'effacer un refus et
      d'injecter une acceptation : invisibles à l'audit local, détectées par le témoin.

Usage : python3 -m rinv.systeme [--evidence FICHIER]
"""

import argparse
import collections
import hashlib
import json
import os
import random
import subprocess
import sys
import tempfile

from outils.evidence import GRAINE, ecrire
from rinv.frame import FrameError, decode, encode
from rinv.gate import Event, InvariantGate, Ledger, sign
from rinv.suture import Supervisor
from rinv.void_monitor import ChannelState, VoidMonitor
from socle_preuve.gamma import Chaine, calculer_hash
from socle_preuve.temoin import ScelleurHMAC, Temoin

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
S = 1_000_000_000
LEDGER_ID = "Γ-demo"
TRAVAILLEUR = "import sys,time\nfrom rinv import beat\nwhile True:\n beat(sys.argv[1]); time.sleep(0.02)"


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
            fh.write(json.dumps(b, sort_keys=True, separators=(",", ":"),
                                ensure_ascii=False) + "\n")


def _rechainer(blocs, depuis):
    prev = blocs[depuis]["prev_hash"]
    for b in blocs[depuis:]:
        b["prev_hash"] = prev
        b["hash"] = calculer_hash(b)
        prev = b["hash"]


class Recepteur:
    """Lit un canal, décode la trame, présente l'événement à la porte.

    Tout refus avant la porte (trame invalide, événement malformé) est inscrit
    au même journal que les verdicts de la porte, et met le canal en quarantaine.
    """

    def __init__(self, porte: InvariantGate, journal: Chaine, moniteur: VoidMonitor):
        self.porte, self.journal, self.moniteur = porte, journal, moniteur

    def _refuser(self, canal, octets, code):
        self.journal.inscrire("trame", "REJETE", code, {
            "canal": os.path.basename(canal),
            "octets_sha256": hashlib.sha256(octets).hexdigest()})
        self.moniteur.quarantine(canal, code)
        return code

    def recevoir(self, canal: str) -> str:
        with open(canal, "rb") as fh:
            octets = fh.read()
        try:
            champs = json.loads(decode(octets))
            event = Event(event_id=champs["event_id"], agent_id=champs["agent_id"],
                          ledger_id=champs["ledger_id"],
                          payload=bytes.fromhex(champs["payload"]),
                          signature_hash=champs["signature_hash"],
                          expected_state_hash=champs["expected_state_hash"])
        except FrameError as e:
            return self._refuser(canal, octets, e.code)
        except (ValueError, KeyError, TypeError):
            return self._refuser(canal, octets, "evenement_malforme")
        v = self.porte.admit(event)
        if v.accepted:
            self.moniteur.touch(canal)
        else:
            self.moniteur.quarantine(canal, v.code)
        return v.code


def emettre(canal: str, event: Event, *, bit_inverse: int | None = None) -> None:
    trame = bytearray(encode(json.dumps({
        "event_id": event.event_id, "agent_id": event.agent_id, "ledger_id": event.ledger_id,
        "payload": event.payload.hex(), "signature_hash": event.signature_hash,
        "expected_state_hash": event.expected_state_hash}).encode()))
    if bit_inverse is not None:
        trame[bit_inverse // 8] ^= 1 << (bit_inverse % 8)
    with open(canal, "wb") as fh:
        fh.write(trame)


def executer(chemin_evidence: str) -> int:
    rng = random.Random(GRAINE)
    controles = []

    def controler(nom, ok, detail=""):
        controles.append({"controle": nom, "ok": bool(ok), "detail": detail})
        print(f"[{'OK' if ok else 'ÉCHEC'}] {nom}" + (f" — {detail}" if detail else ""))

    shm = "/dev/shm" if os.path.isdir("/dev/shm") else None
    with tempfile.TemporaryDirectory() as disque, \
            tempfile.TemporaryDirectory(dir=shm) as volatil:
        secret = os.path.join(disque, "temoin.secret")
        assert _cli("keygen-hmac", secret)[0] == 0
        with open(secret, "rb") as fh:
            scelleur = ScelleurHMAC(fh.read())
        chemins = {nom: (os.path.join(disque, f"{nom}.jsonl"),
                         os.path.join(disque, f"{nom}.temoin.jsonl"))
                   for nom in ("registre", "decisions")}
        registre = Ledger(LEDGER_ID, chemins["registre"][0],
                          temoin=Temoin(chemins["registre"][1], scelleur))
        journal = Chaine(chemins["decisions"][0],
                         temoin=Temoin(chemins["decisions"][1], scelleur))

        horloge = {"t": 0}
        moniteur = VoidMonitor(clock=lambda: horloge["t"], journal=journal)
        cle_agents = os.urandom(32)  # secret partagé des agents autorisés (I₂ = provenance)
        porte = InvariantGate(registre, {"alpha", "beta"}, key=cle_agents, journal=journal)
        recepteur = Recepteur(porte, journal, moniteur)
        canaux = {a: os.path.join(volatil, f"canal-{a}") for a in
                  ("alpha", "beta", "mallory", "gamma")}
        for c in canaux.values():
            open(c, "wb").close()
            moniteur.watch(c)

        def evenement(eid, agent, *, cle=cle_agents, payload=None, attendu=None,
                      ledger=LEDGER_ID, signature=None):
            payload = payload or f"op-{eid}-{rng.randrange(10**6)}".encode()
            return Event(eid, agent, ledger, payload,
                         signature or sign(payload, cle),
                         attendu if attendu is not None else registre.state_hash)

        tete_initiale = registre.state_hash
        e1 = evenement("e1", "alpha")
        scenario = [
            (1, "alpha", e1, {}, "invariants_ok"),
            (2, "alpha", e1, {}, "rejeu_idempotent"),
            (3, "beta", evenement("e2", "beta", attendu=tete_initiale), {}, "etat_perime"),
            (4, "alpha", evenement("e3", "alpha", signature=sign(b"autre chose", cle_agents)),
             {}, "signature_invalide"),
            (5, "beta", evenement("e4", "beta"), {"bit_inverse": rng.randrange(8, 64)},
             "crc_invalide"),
            (6, "mallory", evenement("m1", "mallory", cle=os.urandom(32)), {},
             "agent_non_autorise"),
            (7, "mallory", evenement("m2", "mallory", cle=os.urandom(32)), {},
             "agent_en_quarantaine"),
            (8, "beta", None, {}, "invariants_ok"),       # e5, construit au moment de l'envoi
            (9, "gamma", evenement("g1", "alpha", ledger="Γ-autre"), {}, "registre_etranger"),
            (14, "alpha", None, {}, "invariants_ok"),     # e6
        ]
        receptions = []
        print("— Réceptions")
        for t, agent, event, options, attendu in scenario:
            horloge["t"] = t * S
            if event is None:
                event = evenement(f"e{5 if agent == 'beta' else 6}", agent)
            emettre(canaux[agent], event, **options)
            code = recepteur.recevoir(canaux[agent])
            receptions.append({"t_s": t, "canal": agent, "event_id": event.event_id,
                               "attendu": attendu, "obtenu": code})
            controler(f"t={t:>2} s  canal {agent:<7} {event.event_id:<3} → {attendu}",
                      code == attendu, "" if code == attendu else f"obtenu {code}")

        print("— Void Monitor : 15 s de silence (horloge avancée artificiellement)")
        horloge["t"] = int(15.5 * S)
        purges = sorted(os.path.basename(p) for p in moniteur.sweep())
        controler("canaux purgés : ceux restés sans trame valide 15 s",
                  purges == ["canal-gamma", "canal-mallory"], ", ".join(purges))
        controler("canaux actifs conservés",
                  all(moniteur.state(canaux[a]) is ChannelState.LIVE for a in ("alpha", "beta"))
                  and all(os.path.exists(canaux[a]) for a in ("alpha", "beta")))

        print("— Auto-Suture : 3 processus réels, l'un est tué")
        sup = Supervisor(["N1", "N2", "N3"],
                         lambda nom, hb: subprocess.Popen(
                             [sys.executable, "-c", TRAVAILLEUR, hb], cwd=RACINE),
                         directory=volatil, timeout_ns=5 * S, journal=journal)
        try:
            victime = sup._nodes["N2"].handle
            victime.kill()
            victime.wait()
            cohesion_avant = sup.cohesion()
            recousus = sup.suture()
            cohesion_apres = sup.cohesion()
        finally:
            sup.shutdown()
        controler("cohésion 2/3 puis suture de N2, cohésion 3/3",
                  (cohesion_avant, recousus, cohesion_apres) == (2 / 3, ["N2"], 1.0),
                  f"{cohesion_avant:.3f} → {recousus} → {cohesion_apres:.3f}")

        print("— Preuve : le témoin confirme les deux chaînes")
        verifs = {}
        for nom, (j, t) in chemins.items():
            code, sortie = _cli("verifier", j, "--temoin", t, "--secret", secret)
            verifs[nom] = {"exit": code, "sortie": sortie}
            controler(f"{nom} : intègre et témoin en accord", code == 0, sortie)

        decisions = _lire(chemins["decisions"][0])
        acceptes = [b for b in _lire(chemins["registre"][0]) if b["type"] == "evenement"]
        controler("registre : seules les transitions acceptées (e1, e5, e6)",
                  [b["donnees"]["event_id"] for b in acceptes] == ["e1", "e5", "e6"])
        par_decision = collections.Counter(b["decision"] for b in decisions)
        par_raison = collections.Counter(b["raison"] for b in decisions)
        refus = sum(par_decision[d] for d in ("REJETE", "QUARANTAINE", "PURGE"))
        print(f"   journal : {len(decisions)} décisions — {dict(par_decision)}")

        print("— Attaques sur la preuve")
        attaques = []
        cible = next(i for i, b in enumerate(decisions)
                     if b["raison"] == "agent_non_autorise")
        decisions[cible]["decision"], decisions[cible]["raison"] = "ACCEPTE", "invariants_ok"
        _rechainer(decisions, cible)
        _ecrire(chemins["decisions"][0], decisions)
        local = _cli("verifier", chemins["decisions"][0])
        avec = _cli("verifier", chemins["decisions"][0], "--temoin", chemins["decisions"][1],
                    "--secret", secret)
        attaques.append({"attaque": f"effacer le refus de mallory (bloc {cible}) avec recalcul",
                         "exit_local": local[0], "exit_temoin": avec[0], "sortie": avec[1]})
        controler(f"effacer le refus de mallory : audit local trompé (exit {local[0]}), "
                  f"témoin exit {avec[0]}", local[0] == 0 and avec[0] == 4, avec[1])

        reg = _lire(chemins["registre"][0])
        faux = dict(reg[-1], seq=len(reg), prev_hash=reg[-1]["hash"],
                    donnees={"event_id": "m1", "agent_id": "mallory", "payload": "00",
                             "signature_hash": "0" * 64})
        reg.append(faux)
        _rechainer(reg, len(reg) - 1)
        _ecrire(chemins["registre"][0], reg)
        local = _cli("verifier", chemins["registre"][0])
        avec = _cli("verifier", chemins["registre"][0], "--temoin", chemins["registre"][1],
                    "--secret", secret)
        attaques.append({"attaque": "injecter une transition de mallory dans le registre",
                         "exit_local": local[0], "exit_temoin": avec[0], "sortie": avec[1]})
        controler(f"injecter une transition de mallory : audit local trompé (exit {local[0]}), "
                  f"témoin exit {avec[0]}", local[0] == 0 and avec[0] == 4, avec[1])

    reussis = sum(c["ok"] for c in controles)
    verdict = "OK" if reussis == len(controles) else "ECHEC"
    print(f"\n{reussis}/{len(controles)} contrôles — "
          f"{'TOUT EST OK' if verdict == 'OK' else 'ÉCHEC'}")
    ecrire(chemin_evidence, module="systeme_rinv", phase=1, etiquette="VÉRIFIÉ", verdict=verdict,
           config={"ledger_id": LEDGER_ID, "agents_autorises": ["alpha", "beta"],
                   "purge_apres_s": 15, "noeuds_suture": 3, "crc": "CRC-16/X-25"},
           mesures={"controles": controles, "reussis": reussis,
                    "receptions": receptions,
                    "journal": {"decisions": sum(par_decision.values()),
                                "refus_prouves": refus,
                                "par_decision": dict(sorted(par_decision.items())),
                                "par_raison": dict(sorted(par_raison.items()))},
                    "registre_acceptes": len(acceptes),
                    "canaux_purges": purges,
                    "suture": {"cohesion_avant": cohesion_avant, "recousus": recousus,
                               "cohesion_apres": cohesion_apres},
                    "verification_temoin": verifs,
                    "attaques": attaques},
           limites=["Données synthétiques ; les canaux sont des fichiers locaux de /dev/shm, "
                    "aucune liaison radio ou AFSK réelle.",
                    "Les 15 s du Void Monitor sont simulées par une horloge injectée ; "
                    "l'Auto-Suture, elle, tue et relance de vrais processus.",
                    "Témoin local : le secret vit sur la même machine que les chaînes (§3.2).",
                    "I₂ repose sur un secret HMAC partagé par les agents autorisés : un agent "
                    "autorisé peut signer au nom d'un autre.",
                    "La quarantaine d'agent est en mémoire ; elle est journalisée mais perdue "
                    "au redémarrage de la porte."])
    return 0 if verdict == "OK" else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python3 -m rinv.systeme")
    ap.add_argument("--evidence", default=os.path.join(os.path.dirname(__file__),
                                                       "systeme_evidence.json"))
    return executer(ap.parse_args(argv).evidence)


if __name__ == "__main__":
    sys.exit(main())
