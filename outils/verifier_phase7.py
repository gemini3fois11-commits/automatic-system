"""Vérification de la phase 7 (blueprint §12) : télégraphe scellé + console navigateur."""

import json
import os
import subprocess
import sys
import tempfile

from outils.evidence import GRAINE, ecrire
from socle_preuve.gamma import Chaine
from socle_preuve.temoin import ScelleurHMAC, Temoin, verifier_temoin
from telegraphe.transport import Recepteur, emettre

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main() -> int:
    controles = []

    def c(nom, ok, detail=""):
        controles.append({"controle": nom, "ok": bool(ok), "detail": detail})
        print(f"[{'OK' if ok else 'ÉCHEC'}] {nom}" + (f" — {detail}" if detail else ""))

    with tempfile.TemporaryDirectory() as tmp:
        secret = os.path.join(tmp, "s"); open(os.open(secret, os.O_WRONLY | os.O_CREAT, 0o600), "wb").write(os.urandom(32))
        with open(secret, "rb") as fh:
            scelleur = ScelleurHMAC(fh.read())
        journal_chemin = os.path.join(tmp, "j.jsonl")
        temoin_chemin = os.path.join(tmp, "j.temoin.jsonl")
        journal = Chaine(journal_chemin, temoin=Temoin(temoin_chemin, scelleur))
        r = Recepteur(journal)
        verdicts = [r.recevoir(emettre(i, f"message {i}")) for i in (1, 2, 3)]
        c("télégraphe : 3 trames scellées dans Γ", all(v["accepte"] for v in verdicts))
        rap = verifier_temoin(journal_chemin, temoin_chemin, scelleur)
        c("témoin HMAC en accord sur chaque bloc scellé", rap.accord, str(rap))

    r = subprocess.run([sys.executable, "-m", "console.generer"], cwd=RACINE,
                       capture_output=True, text=True, timeout=60)
    c("console générée en HTML statique auto-contenu", r.returncode == 0, r.stdout.strip())
    r = subprocess.run(["node", "console/verifier.js"], cwd=RACINE, capture_output=True, text=True, timeout=120)
    try:
        data = json.loads(r.stdout)
    except ValueError:
        data = {}
    c("vérification Chromium : 0 erreur console (desktop + mobile)",
      data.get("desktop", {}).get("erreurs") == [] and data.get("mobile", {}).get("erreurs") == [])
    c("aucun débordement horizontal à 375 px et 1280 px",
      data.get("mobile", {}).get("debordement_px", 999) <= 0 and data.get("desktop", {}).get("debordement_px", 999) <= 0)
    c("tous les liens d'évidence existent", data.get("liens", {}).get("manquants") == [])
    c("≥ 25 modules listés", data.get("desktop", {}).get("modules", 0) >= 25)
    c("mission affichée comme proposée (§1.1)",
      "proposée" in data.get("desktop", {}).get("missionText", ""))

    reussis = sum(x["ok"] for x in controles)
    verdict = "OK" if reussis == len(controles) else "ECHEC"
    print(f"\n{reussis}/{len(controles)} contrôles — {'TOUT EST OK' if verdict == 'OK' else 'ÉCHEC'}")
    ecrire(os.path.join(RACINE, "outils", "phase7_evidence.json"),
           module="presentation", phase=7, etiquette="VÉRIFIÉ", verdict=verdict,
           graine=GRAINE,
           config={"navigateur": "Chromium (Playwright pré-installé)",
                   "viewports": {"desktop": "1280x800", "mobile": "375x812"},
                   "vecteurs_crc": "CRC-16/X-25(123456789) = 0x906E"},
           mesures={"controles": controles, "reussis": reussis, "navigateur": data},
           limites=["Chromium headless : d'autres moteurs (WebKit, Gecko) ne sont pas joués.",
                    "La page est un instantané ; l'état du dépôt peut diverger après génération.",
                    "Voie microphone du télégraphe non jouée (restée [EXPÉRIMENTAL])."])
    return 0 if verdict == "OK" else 1


if __name__ == "__main__":
    sys.exit(main())
