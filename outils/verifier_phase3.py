"""Vérification de la phase 3 (blueprint §12) : les trois portes, en vrai.

Démarre GARDIEN (8090), passerelle (8077) et terminal (8076) sur leurs ports officiels,
avec un état temporaire ; contrôle par `ss -tln` qu'ils n'écoutent que sur 127.0.0.1 ;
sonde les refus ; cherche des secrets dans les journaux ; arrête tout ; rejoue les suites.
Écrit outils/phase3_evidence.json.
"""

import http.client
import json
import os
import re
import signal
import socket
import subprocess
import sys
import tempfile
import time

from outils.evidence import ecrire

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PORTES = {"agent_guard.guard": 8090, "cryoloop_gateway.gateway": 8077, "terminal_auth.server": 8076}
MDP = "secret-de-verification-phase3"
SUITES = ["socle_preuve.test_auth", "agent_guard.test_guard", "cryoloop_gateway.test_gateway",
          "terminal_auth.test_terminal", "runtime.test_superviseur"]


def ecoutes_noyau(ports) -> dict[int, list[str]]:
    """Sockets TCP en écoute (état 0A), lues dans /proc/net/tcp{,6} comme le fait ss."""
    ecoutes = {}
    for fichier, v6 in (("/proc/net/tcp", False), ("/proc/net/tcp6", True)):
        try:
            with open(fichier) as fh:
                lignes = fh.read().splitlines()[1:]
        except FileNotFoundError:
            continue
        for ligne in lignes:
            champs = ligne.split()
            adresse, port_hex = champs[1].split(":")
            if champs[3] != "0A" or int(port_hex, 16) not in ports:
                continue
            brut = bytes.fromhex(adresse)
            if v6:
                mots = [brut[i:i + 4][::-1] for i in range(0, 16, 4)]
                ip = socket.inet_ntop(socket.AF_INET6, b"".join(mots))
            else:
                ip = socket.inet_ntoa(brut[::-1])
            ecoutes.setdefault(int(port_hex, 16), []).append(ip)
    return ecoutes


def attendre_port(port, ouvert=True, delai=10):
    fin = time.monotonic() + delai
    while time.monotonic() < fin:
        with socket.socket() as s:
            if (s.connect_ex(("127.0.0.1", port)) == 0) == ouvert:
                return True
        time.sleep(0.05)
    return False


def req(port, methode, chemin, corps=None):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    conn.request(methode, chemin, body=None if corps is None else json.dumps(corps),
                 headers={"Host": f"127.0.0.1:{port}", "Content-Type": "application/json"})
    r = conn.getresponse()
    d = r.read()
    conn.close()
    return r.status, json.loads(d) if d else None


def main() -> int:
    controles = []

    def controle(nom, ok, detail=""):
        controles.append({"controle": nom, "ok": bool(ok), "detail": detail})
        print(f"[{'OK' if ok else 'ÉCHEC'}] {nom}" + (f" — {detail}" if detail else ""))

    occupes = [p for p in PORTES.values() if attendre_port(p, True, 0.2)]
    if occupes:
        controle("ports officiels libres avant le test", False, f"occupés : {occupes}")
    with tempfile.TemporaryDirectory() as tmp:
        procs = {}
        for module, port in PORTES.items():
            args = {"agent_guard.guard": ["--journal", os.path.join(tmp, "guard.jsonl")],
                    "cryoloop_gateway.gateway": ["--etat", os.path.join(tmp, "passerelle")],
                    "terminal_auth.server": ["--etat", os.path.join(tmp, "terminal")]}[module]
            procs[module] = subprocess.Popen([sys.executable, "-m", module, *args], cwd=RACINE,
                                             stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        try:
            controle("les trois portes démarrent", all(attendre_port(p) for p in PORTES.values()))
            ecoutes = ecoutes_noyau(set(PORTES.values()))
            controle("table TCP du noyau (/proc/net/tcp, source de ss -tln) : 8090, 8077 et 8076 n'écoutent que sur 127.0.0.1",
                     set(ecoutes) == set(PORTES.values())
                     and all(adr == ["127.0.0.1"] for adr in ecoutes.values()),
                     json.dumps(ecoutes))
            controle("terminal : GET /api/exec sans session → 401, rien exécuté",
                     req(8076, "GET", "/api/exec?cmd=id")[0] == 401)
            controle("terminal : SETUP_MODE au démarrage", req(8076, "GET", "/api/etat")[1]["setup_mode"])
            req(8076, "POST", "/api/setup", {"mot_de_passe": MDP})
            controle("terminal : POST /api/exec sans session → 401",
                     req(8076, "POST", "/api/exec", {"commande": "echo x"})[0] == 401)
            req(8076, "POST", "/api/login", {"mot_de_passe": MDP + "-faux"})
            etat = req(8077, "GET", "/api/etat")[1]
            controle("passerelle : non initialisée (SETUP_MODE, aucune clé épinglée)",
                     etat == {"setup_mode": True, "cle_epinglee": False, "execute": False}, json.dumps(etat))
            req(8077, "POST", "/api/setup", {"mot_de_passe": MDP})
            code, statut = req(8090, "GET", "/api/status")
            controle("GARDIEN : /api/status répond, chaîne intègre", code == 200 and statut["chaine"]["integre"])
        finally:
            for p in procs.values():
                p.send_signal(signal.SIGINT)
            for p in procs.values():
                try:
                    p.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    p.kill()
        controle("arrêt propre : ports libérés", all(attendre_port(p, False) for p in PORTES.values()))
        fuites = []
        for dossier, _, noms in os.walk(tmp):
            for nom in noms:
                if nom.endswith(".jsonl"):
                    with open(os.path.join(dossier, nom), encoding="utf-8") as fh:
                        if MDP in fh.read():
                            fuites.append(nom)
        controle("aucun mot de passe dans les journaux d'audit", not fuites, ", ".join(fuites))

    r = subprocess.run([sys.executable, "-W", "error", "-m", "unittest", *SUITES], cwd=RACINE,
                       capture_output=True, text=True)
    m = re.search(r"Ran (\d+) tests", r.stderr)
    controle("suites de la phase 3", r.returncode == 0, f"{m.group(1) if m else '?'} tests, "
             f"{'OK' if r.returncode == 0 else r.stderr.strip().splitlines()[-1]}")
    with open(os.path.join(RACINE, "agent_guard", "guard_evidence.json"), encoding="utf-8") as fh:
        garde = json.load(fh)
    controle("GARDIEN : banc de requêtes réelles", garde["verdict"] == "OK",
             f"{garde['mesures']['reussis']}/{len(garde['mesures']['cas'])} cas")
    reussis = sum(c["ok"] for c in controles)
    verdict = "OK" if reussis == len(controles) else "ECHEC"
    print(f"\n{reussis}/{len(controles)} contrôles — {'TOUT EST OK' if verdict == 'OK' else 'ÉCHEC'}")
    ecrire(os.path.join(RACINE, "outils", "phase3_evidence.json"), module="portes_terrain", phase=3,
           etiquette="VÉRIFIÉ", verdict=verdict, config={"ports": PORTES, "suites": SUITES},
           mesures={"controles": controles, "reussis": reussis, "tests": int(m.group(1)) if m else None},
           limites=["Trafic vers les hôtes publics de l'allowlist non joué (proxy sortant HTTPS seul).",
                    "Passerelle et terminal restent non initialisés : mot de passe et clé appartiennent "
                    "au propriétaire ; la vérification a utilisé un état temporaire, détruit ensuite.",
                    "Pas de TLS sur les portes : boucle locale uniquement."])
    return 0 if verdict == "OK" else 1


if __name__ == "__main__":
    sys.exit(main())
