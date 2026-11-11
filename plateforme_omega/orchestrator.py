"""Orchestrateur de la plateforme (blueprint §6.1).

Lance toutes les suites en parallèle, plus le balayage HERMÈS (seuil lâche {50, 100, 200} ×
entraînement {90, 150}) ; reprend le balayage de l'essaim ; calcule Ω Q à partir des évidences ;
écrit UN fichier d'évidence consolidé et régénère le tableau de bord.

  python3 -m plateforme_omega.orchestrator [--out plateforme_evidence.json]
"""

import argparse
import concurrent.futures as cf
import html
import os
import subprocess
import sys
import tempfile
import time

from outils.evidence import ecrire, lire
from plateforme_omega.commun import DOSSIER, lignes_de_code
from plateforme_omega.omega_q import evaluer

RACINE = os.path.dirname(DOSSIER)
PY = [sys.executable, "-m"]
UNITTEST = [sys.executable, "-W", "error", "-m", "unittest"]

# Les 21 suites du blueprint (§6.2) : (commande, évidence produite ou None, fichiers évalués par Ω Q)
SUITES_BLUEPRINT = {
    "passerelle": (UNITTEST + ["cryoloop_gateway.test_gateway"], None, ["../cryoloop_gateway/gateway.py"]),
    "validateur": (PY + ["cryoloop", "banc"], "cryoloop/cryoloop_evidence.json", ["../cryoloop/validateur.py"]),
    "rag": (PY + ["rag_wiki.rag", "--eval"], "rag_wiki/rag_evidence.json", ["../rag_wiki/rag.py"]),
    "pinning": (PY + ["rag_wiki.pinning", "--eval"], "rag_wiki/pinning_evidence.json", ["../rag_wiki/pinning.py"]),
    "fusion": (PY + ["rag_wiki.fusion", "--eval"], "rag_wiki/fusion_mrr.json", ["../rag_wiki/fusion.py"]),
    "hermes": (PY + ["omega_hermes.loop"], "omega_hermes/hermes_evidence.json",
               ["../omega_hermes/twin.py", "../omega_hermes/alice.py", "../omega_hermes/eyes.py",
                "../omega_hermes/bob.py", "../omega_hermes/hermes.py", "../omega_hermes/loop.py"]),
    "ai_mode": (PY + ["omega_hermes.phase4", "--module", "ai_mode"], "omega_hermes/ai_mode_evidence.json",
                ["../omega_hermes/ai_mode.py"]),
    "scaling": (PY + ["omega_hermes.scaling"], "omega_hermes/scaling_evidence.json", ["../omega_hermes/scaling.py"]),
    "reverie": (PY + ["omega_hermes.phase4", "--module", "reverie"], "omega_hermes/reverie_evidence.json",
                ["../omega_hermes/reverie.py"]),
    "tls": (PY + ["plateforme_omega.tls"], "plateforme_omega/tls_evidence.json", ["tls.py"]),
    "omega_q": (PY + ["plateforme_omega.omega_q"], "plateforme_omega/omega_q_evidence.json", ["omega_q.py"]),
    "mtd": (PY + ["plateforme_omega.mtd"], "plateforme_omega/mtd_evidence.json", ["mtd.py"]),
    "watcher": (PY + ["plateforme_omega.watcher"], "plateforme_omega/watcher_evidence.json", ["watcher.py"]),
    "agi": (PY + ["plateforme_omega.agi"], "plateforme_omega/agi_evidence.json", ["agi.py"]),
    "evasion": (PY + ["omega_hermes.phase4", "--module", "evasion"], "omega_hermes/evasion_evidence.json",
                ["../omega_hermes/evasion.py"]),
    "guardian": (PY + ["omega_hermes.phase4", "--module", "guardian"], "omega_hermes/guardian_evidence.json",
                 ["../omega_hermes/guardian.py"]),
    "prng": (PY + ["plateforme_omega.prng"], "plateforme_omega/prng_evidence.json",
             ["prng.py", "prng/cryoloop_prng.cpp"]),
    "codage": (PY + ["plateforme_omega.codage"], "plateforme_omega/codage_evidence.json", ["codage.py"]),
    "brouillons": (PY + ["omega_hermes.phase4", "--module", "brouillons"], "omega_hermes/brouillons_evidence.json",
                   ["../omega_hermes/brouillons.py"]),
    "attrape": (PY + ["omega_hermes.phase4", "--module", "attrape"], "omega_hermes/attrape_evidence.json",
                ["../omega_hermes/attrape.py"]),
    "hyper": (PY + ["plateforme_omega.hyper"], "plateforme_omega/hyper_evidence.json", ["hyper.py"]),
}
# Suites ajoutées par cette reconstruction, au-delà des 21 du blueprint.
SUITES_AJOUTEES = {
    "socle_preuve": (PY + ["socle_preuve", "demo"], "socle_preuve/preuve_evidence.json",
                     ["../socle_preuve/gamma.py", "../socle_preuve/temoin.py", "../socle_preuve/ed25519.py"]),
    "systeme_rinv": (PY + ["rinv.systeme"], "rinv/systeme_evidence.json", ["../rinv/gate.py", "../rinv/systeme.py"]),
    "gardien": (PY + ["agent_guard.banc"], "agent_guard/guard_evidence.json", ["../agent_guard/guard.py"]),
    "terminal": (UNITTEST + ["terminal_auth.test_terminal"], None, ["../terminal_auth/server.py"]),
    "runtime": (UNITTEST + ["runtime.test_superviseur"], None, ["../runtime/superviseur.py"]),
    "swarm": (PY + ["omega_hermes.phase4", "--module", "swarm"], "omega_hermes/swarm_evidence.json",
              ["../omega_hermes/swarm.py"]),
    "rubik": (PY + ["plateforme_omega.rubik"], "plateforme_omega/rubik_evidence.json", ["rubik.py"]),
    "distribue": (PY + ["plateforme_omega.distribue"], "plateforme_omega/distribue_evidence.json", ["distribue.py"]),
    "etoile": (PY + ["plateforme_omega.etoile"], "plateforme_omega/etoile_evidence.json", ["etoile.py"]),
}
BALAYAGE_HERMES = [(f, e) for f in (50, 100, 200) for e in (90, 150)]


def _module_present(commande) -> bool:
    if "unittest" in commande:
        return True
    module = commande[commande.index("-m") + 1].replace(".", "/")
    return os.path.exists(os.path.join(RACINE, module + ".py")) or os.path.isdir(os.path.join(RACINE, module))


def lancer(nom, commande, delai=600):
    if not _module_present(commande):
        return {"suite": nom, "statut": "ABSENTE", "code": None, "duree_s": 0.0, "fin": "module non construit"}
    t0 = time.perf_counter()
    try:
        r = subprocess.run(commande, cwd=RACINE, capture_output=True, text=True, timeout=delai)
        code, sortie = r.returncode, (r.stdout + r.stderr).strip().splitlines()
    except subprocess.TimeoutExpired:
        code, sortie = -1, ["délai dépassé"]
    return {"suite": nom, "statut": "OK" if code == 0 else "ECHEC", "code": code,
            "duree_s": time.perf_counter() - t0, "fin": sortie[-1] if sortie else ""}


def omega_q(suites: dict, resultats: dict) -> list[dict]:
    evaluations = []
    for nom, (_, evidence, fichiers) in suites.items():
        r = resultats[nom]
        if r["statut"] == "ABSENTE":
            continue
        mesures, criteres = {}, None
        if evidence and os.path.exists(os.path.join(RACINE, evidence)):
            doc = lire(os.path.join(RACINE, evidence))
            mesures = doc["mesures"]
            criteres = mesures.get("criteres") or mesures.get("cas") or mesures.get("controles")
        if isinstance(criteres, list) and criteres:
            taux_echec = sum(not c["ok"] for c in criteres) / len(criteres)
        else:
            taux_echec = 0.0 if r["statut"] == "OK" else 1.0
        chemins = [os.path.normpath(os.path.join(DOSSIER, f)) for f in fichiers]
        manquants = [c for c in chemins if not os.path.exists(c)]
        if manquants:
            raise FileNotFoundError(f"Ω Q : fichiers évalués introuvables pour {nom} : {manquants}")
        loc = lignes_de_code(*chemins)
        gain = mesures.get("gain") if isinstance(mesures.get("gain"), (int, float)) else None
        reprise = mesures.get("reprise") if isinstance(mesures.get("reprise"), (int, float)) else None
        q = evaluer(taux_echec=taux_echec, gain=gain, reprise=reprise, loc=loc, runtime_s=r["duree_s"])
        evaluations.append({"module": nom, "loc": loc, "runtime_s": round(r["duree_s"], 2)} | q)
    return evaluations


def tableau_de_bord(doc: dict, chemin: str):
    m = doc["mesures"]
    lignes = "".join(
        f"<tr><td>{html.escape(s['suite'])}</td><td class='{s['statut'].lower()}'>{s['statut']}</td>"
        f"<td>{s['duree_s']:.1f} s</td><td>{html.escape(s['fin'][:90])}</td></tr>" for s in m["suites"])
    q = "".join(f"<tr><td>{html.escape(e['module'])}</td><td>{e['Q']:+.2f}</td><td>{e['decision']}</td>"
                f"<td>S {e['S']:.2f} · P {e['P']:.2f} · R {e['R']:.2f} · C {e['C']:.2f}</td>"
                f"<td>{', '.join(e['drapeaux'])}</td></tr>" for e in m["omega_q"])
    b = "".join(f"<tr><td>{x['facteur_lache']}</td><td>{x['entrainement']}</td><td>{x['score']}</td></tr>"
                for x in m["balayage_hermes"])
    page = f"""<!doctype html><html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Plateforme Omega</title><style>
:root{{--fond:#f7f7f5;--texte:#1d1d1b;--doux:#6b6b66;--cadre:#ddd;--ok:#1b7a3a;--ko:#b3261e}}
@media (prefers-color-scheme:dark){{:root{{--fond:#151514;--texte:#ecece8;--doux:#a0a09a;--cadre:#333;--ok:#6fcf8f;--ko:#ff8a80}}}}
body{{margin:0;background:var(--fond);color:var(--texte);font:15px/1.5 system-ui,sans-serif}}
main{{max-width:1000px;margin:0 auto;padding:24px 16px}}table{{width:100%;border-collapse:collapse;margin:8px 0 24px}}
td,th{{border-bottom:1px solid var(--cadre);padding:6px 8px;text-align:left;vertical-align:top}}
.ok{{color:var(--ok)}}.echec,.absente{{color:var(--ko)}}.note{{color:var(--doux)}}
.tableau{{overflow-x:auto}}</style></head><body><main>
<h1>Plateforme Omega — cycle du {html.escape(doc['execution']['genere_le'])}</h1>
<p class="note">Généré depuis plateforme_evidence.json — aucun chiffre saisi à la main. Étiquette : [{doc['etiquette']}].</p>
<p><strong>{m['suites_ok']}/{m['suites_total']}</strong> suites OK · durée murale {m['duree_murale_s']:.1f} s ·
somme des durées {m['duree_sequentielle_estimee_s']:.1f} s · gain parallèle ×{m['gain_parallele']:.2f}
· Ω Q : {m['omega_q_decisions']}</p>
<h2>Suites</h2><div class="tableau"><table><tr><th>Suite</th><th>Statut</th><th>Durée</th><th>Dernière ligne</th></tr>{lignes}</table></div>
<h2>Ω Q</h2><div class="tableau"><table><tr><th>Module</th><th>Q</th><th>Décision</th><th>Composantes</th><th>Drapeaux</th></tr>{q}</table></div>
<h2>Balayage HERMÈS</h2><div class="tableau"><table><tr><th>Facteur lâche</th><th>Entraînement / classe</th><th>Score</th></tr>{b}</table></div>
</main></body></html>"""
    with open(chemin, "w", encoding="utf-8") as fh:
        fh.write(page)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python3 -m plateforme_omega.orchestrator")
    ap.add_argument("--out", default=os.path.join(DOSSIER, "plateforme_evidence.json"))
    ap.add_argument("--paralleles", type=int, default=os.cpu_count() or 2)
    a = ap.parse_args(argv)
    suites = SUITES_BLUEPRINT | SUITES_AJOUTEES
    with tempfile.TemporaryDirectory() as tmp:
        travaux = {nom: (cmd,) for nom, (cmd, _, _) in suites.items()}
        for f, e in BALAYAGE_HERMES:
            travaux[f"balayage_hermes_{f}_{e}"] = (PY + ["omega_hermes.loop", "--facteur-lache", str(f),
                                                         "--entrainement", str(e), "--evidence",
                                                         os.path.join(tmp, f"h_{f}_{e}.json")],)
        t0 = time.perf_counter()
        with cf.ThreadPoolExecutor(max_workers=a.paralleles) as ex:
            futurs = {nom: ex.submit(lancer, nom, *args) for nom, args in travaux.items()}
            res = {nom: f.result() for nom, f in futurs.items()}
        murale = time.perf_counter() - t0
        balayage = []
        for f, e in BALAYAGE_HERMES:
            chemin = os.path.join(tmp, f"h_{f}_{e}.json")
            g = lire(chemin)["mesures"]["global"] if os.path.exists(chemin) else None
            balayage.append({"facteur_lache": f, "entrainement": e,
                             "score": round(g["score"], 4) if g else None,
                             "rejet_inconnu": g["rejet_inconnu"] if g else None, "fpr": g["fpr"] if g else None})
    sequentiel = sum(r["duree_s"] for r in res.values())
    lignes = [res[n] for n in suites]
    bp = [res[n] for n in SUITES_BLUEPRINT]
    evaluations = omega_q(suites, res)
    decisions = {d: sum(e["decision"] == d for e in evaluations) for d in ("ACCEPTER", "REVOIR", "REJETER")}
    essaim = lire(os.path.join(RACINE, "omega_hermes/swarm_evidence.json"))["mesures"]["balayage"] \
        if os.path.exists(os.path.join(RACINE, "omega_hermes/swarm_evidence.json")) else None
    meilleur = max((b for b in balayage if b["score"] is not None), key=lambda b: b["score"], default=None)
    mesures = {"suites": lignes, "suites_total": len(lignes), "suites_ok": sum(r["statut"] == "OK" for r in lignes),
               "blueprint": {"total": len(bp), "ok": sum(r["statut"] == "OK" for r in bp),
                             "absentes": [r["suite"] for r in bp if r["statut"] == "ABSENTE"],
                             "echecs": [r["suite"] for r in bp if r["statut"] == "ECHEC"]},
               "duree_murale_s": murale, "duree_sequentielle_estimee_s": sequentiel,
               "gain_parallele": sequentiel / murale, "paralleles": a.paralleles,
               "balayage_hermes": balayage, "meilleur_balayage": meilleur, "balayage_essaim": essaim,
               "omega_q": evaluations, "omega_q_decisions": decisions}
    ok = mesures["suites_ok"] == mesures["suites_total"]
    doc = ecrire(a.out, module="plateforme", phase=5, etiquette="VÉRIFIÉ", verdict="OK" if ok else "ECHEC",
                 config={"suites_blueprint": list(SUITES_BLUEPRINT), "suites_ajoutees": list(SUITES_AJOUTEES),
                         "balayage_hermes": BALAYAGE_HERMES},
                 mesures=mesures,
                 limites=["Gain parallèle = somme des durées / durée murale, sur la machine indiquée ; "
                          "c'est un rapport mesuré, pas une promesse.",
                          "Ω Q : S est la part de critères réussis de chaque évidence ; P et R ne valent que "
                          "si l'évidence mesure un gain ou une reprise, sinon 0 avec drapeau."])
    tableau_de_bord(doc, os.path.join(DOSSIER, "plateforme_omega.html"))
    for r in lignes:
        print(f"[{r['statut']:7s}] {r['suite']:14s} {r['duree_s']:6.1f} s  {r['fin'][:80]}")
    print(f"\nSuites du blueprint : {mesures['blueprint']['ok']}/{mesures['blueprint']['total']} OK "
          f"(absentes : {', '.join(mesures['blueprint']['absentes']) or 'aucune'} ; "
          f"échecs : {', '.join(mesures['blueprint']['echecs']) or 'aucun'})")
    print(f"Toutes suites : {mesures['suites_ok']}/{mesures['suites_total']} · murale {murale:.1f} s · "
          f"séquentiel estimé {sequentiel:.1f} s · gain ×{mesures['gain_parallele']:.2f} sur {a.paralleles} voies")
    print("Balayage HERMÈS : " + " · ".join(f"{b['facteur_lache']}×/{b['entrainement']} → {b['score']}" for b in balayage))
    print(f"Ω Q sur {len(evaluations)} évaluations : {decisions}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
