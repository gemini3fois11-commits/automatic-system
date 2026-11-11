"""Distribué (blueprint §6.2, §6.4) : des tâches réparties sur de vrais processus, avec
fautes injectées. Un travailleur plante (« boom »), un autre se tait (« silence ») : le
coordinateur détecte, met le travailleur fautif à l'écart et réattribue la tâche. Toutes
les tâches aboutissent, au résultat près, et le gain parallèle est mesuré.
"""

import concurrent.futures as cf
import hashlib
import os
import subprocess
import sys
import threading
import time

from plateforme_omega.commun import conclure, sortir

TRAVAILLEUR = r"""
import hashlib, sys, time
graine, tours, faute = sys.argv[1], int(sys.argv[2]), sys.argv[3]
if faute == "boom":
    raise SystemExit(3)
if faute == "silence":
    time.sleep(3600)
h = graine.encode()
for _ in range(tours):
    h = hashlib.sha256(h).digest()
print(h.hex())
"""
MULTIPLE_DELAI = 4      # silence = 4 × la durée médiane d'une tâche saine, mesurée


def attendu(graine: str, tours: int) -> str:
    h = graine.encode()
    for _ in range(tours):
        h = hashlib.sha256(h).digest()
    return h.hex()


class Coordinateur:
    def __init__(self, travailleurs: dict[str, str], delai_s: float = 60.0):
        self.delai_s = delai_s
        self.fautes = dict(travailleurs)            # identité → faute injectée ("", "boom", "silence")
        self.ecartes: set[str] = set()
        self.verrou = threading.Lock()
        self.journal: list[dict] = []

    def _executer(self, ident, graine, tours):
        p = subprocess.Popen([sys.executable, "-c", TRAVAILLEUR, graine, str(tours), self.fautes[ident]],
                             stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        try:
            sortie, _ = p.communicate(timeout=self.delai_s)
        except subprocess.TimeoutExpired:
            p.kill()
            p.wait()
            return None, "silence"
        return (sortie.strip(), None) if p.returncode == 0 else (None, f"code_{p.returncode}")

    def tache(self, i, graine, tours):
        tentatives = 0
        while True:
            with self.verrou:
                sains = [t for t in self.fautes if t not in self.ecartes]
                ident = sains[(i + tentatives) % len(sains)]
            resultat, faute = self._executer(ident, graine, tours)
            if faute is None:
                return resultat, ident, tentatives
            with self.verrou:
                self.ecartes.add(ident)
                self.journal.append({"tache": i, "travailleur": ident, "faute": faute})
            tentatives += 1

    def lancer(self, taches, paralleles):
        with cf.ThreadPoolExecutor(max_workers=paralleles) as ex:
            return list(ex.map(lambda a: self.tache(*a), [(i, g, t) for i, (g, t) in enumerate(taches)]))


def mesurer(n_taches=16, tours=400_000) -> dict:
    taches = [(f"tache-{i}", tours) for i in range(n_taches)]
    travailleurs = {f"T{k}": "" for k in range(6)} | {"T2": "boom", "T4": "silence"}
    t0 = time.perf_counter()
    sequentiel = Coordinateur({"T0": ""}).lancer(taches, 1)
    duree_seq = time.perf_counter() - t0
    delai = MULTIPLE_DELAI * duree_seq / n_taches
    c = Coordinateur(travailleurs, delai)
    t0 = time.perf_counter()
    res = c.lancer(taches, min(4, os.cpu_count() or 1))
    duree_par = time.perf_counter() - t0
    justes = all(r == attendu(g, t) for (r, _, _), (g, t) in zip(res, taches))
    injectees = {i for i, f in travailleurs.items() if f}
    reprises = {j["travailleur"] for j in c.journal} & injectees
    return {"taches": n_taches, "justes": justes, "identiques_au_sequentiel": [r for r, _, _ in res] == [r for r, _, _ in sequentiel],
            "fautes_injectees": sorted(injectees), "fautes_detectees": c.journal,
            "reprise": len(reprises) / len(injectees), "ecartes": sorted(c.ecartes),
            "duree_sequentielle_s": duree_seq, "duree_parallele_s": duree_par,
            "gain": duree_seq / duree_par, "paralleles": min(4, os.cpu_count() or 1),
            "delai_silence_s": delai}


def main() -> int:
    m = mesurer()
    return conclure("distribue", [
        ("toutes les tâches aboutissent, résultats justes", m["justes"] and m["identiques_au_sequentiel"], ""),
        ("2/2 fautes injectées détectées et reprises", m["reprise"] == 1.0,
         ", ".join(f"{j['travailleur']}:{j['faute']}" for j in m["fautes_detectees"])),
        ("seuls les travailleurs fautifs sont écartés", m["ecartes"] == m["fautes_injectees"], str(m["ecartes"])),
        ("gain parallèle mesuré > 1 malgré les fautes", m["gain"] > 1.0, f"×{m['gain']:.2f} sur {m['paralleles']} voies"),
    ], m, ["Un seul hôte : processus locaux, pas de réseau, pas de consensus distribué.",
           f"Le silence est détecté par délai ({MULTIPLE_DELAI} × la durée médiane d'une tâche) : un "
           "travailleur lent est traité comme muet.",
           "Avant détection, un travailleur muet peut recevoir plusieurs tâches en parallèle : chacune coûte "
           "un délai complet."])


if __name__ == "__main__":
    sortir(main())
