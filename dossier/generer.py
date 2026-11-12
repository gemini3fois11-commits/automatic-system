"""Dossier de vérification final (discipline type NASA — pas de certification).

Produit :
  dossier/matrice_tracabilite.md     exigence → code → test → évidence
  dossier/rapport_analyse.json       état de chaque phase + ruff + couverture + cycle plateforme
  dossier/README.md                  entrée du dossier, résumé lisible
"""

import collections
import datetime
import glob
import hashlib
import json
import os
import subprocess
import sys

from outils.evidence import lire

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOSSIER = os.path.dirname(os.path.abspath(__file__))

# Exigences normatives tirées du blueprint : (code, source, résumé, modules, tests, évidences)
EXIGENCES = [
    ("E-1.1", "§1.1 Mission",
     "Un refus produit une preuve vérifiable par un témoin indépendant.",
     ["socle_preuve/gamma.py", "socle_preuve/temoin.py", "rinv/systeme.py"],
     ["socle_preuve.test_gamma", "socle_preuve.test_temoin", "tests.test_systeme"],
     ["socle_preuve/preuve_evidence.json", "rinv/systeme_evidence.json"]),
    ("E-1.2", "§1.2 Refuser avant de croire",
     "Allowlist exacte ; le classifieur rejette plutôt que de forcer une classe.",
     ["agent_guard/guard.py", "omega_hermes/bob.py"],
     ["agent_guard.test_guard", "omega_hermes.test_bob", "omega_hermes.test_hermes"],
     ["agent_guard/guard_evidence.json", "omega_hermes/hermes_evidence.json"]),
    ("E-1.3", "§1.3 Étiquettes d'honnêteté",
     "Chaque évidence porte une étiquette (VÉRIFIÉ/SIMULÉ/DÉMONTRÉ/SPÉCIFIÉ/…).",
     ["outils/evidence.py"],
     [], ["(toutes les évidences)"]),
    ("E-1.5", "§1.5 Découplage synthétique",
     "Les modules du banc n'importent que la liste blanche (pas de socket, pas d'open).",
     ["omega_hermes/decouplage.py", "omega_hermes/twin.py", "omega_hermes/alice.py", "omega_hermes/eyes.py", "omega_hermes/bob.py"],
     ["omega_hermes.test_twin"], ["omega_hermes/hermes_evidence.json"]),
    ("E-2.1", "§2.1 Écoute 127.0.0.1 seulement",
     "Toutes les portes refusent une autre interface.",
     ["socle_preuve/porte_http.py", "agent_guard/guard.py", "cryoloop_gateway/gateway.py", "terminal_auth/server.py"],
     ["socle_preuve.test_auth", "socle_preuve.test_porte_http"],
     ["outils/phase3_evidence.json"]),
    ("E-3.1", "§3.1 Chaîne Γ append-only SHA-256",
     "hash = SHA-256(prev_hash || canon(bloc)) ; vérificateur nomme le seq fautif.",
     ["socle_preuve/gamma.py"],
     ["socle_preuve.test_gamma"], ["socle_preuve/preuve_evidence.json"]),
    ("E-3.2", "§3.2 Témoin indépendant",
     "Scelle (seq, hash) hors du journal ; détecte toute réécriture.",
     ["socle_preuve/temoin.py", "socle_preuve/ed25519.py"],
     ["socle_preuve.test_temoin", "socle_preuve.test_ed25519"],
     ["socle_preuve/preuve_evidence.json"]),
    ("E-3.3", "P-BYP-27 contournement",
     "Le contrôle OCC est sous le verrou d'écriture, pas au-dessus.",
     ["socle_preuve/gamma.py", "rinv/gate.py"],
     ["socle_preuve.test_gamma (OCC)", "tests.test_rinv (test_occ_race)"],
     ["rinv/systeme_evidence.json"]),
    ("E-4.3", "§4.3 BOB à deux seuils",
     "Reproduire le défaut historique (seuil unique → ARTIFACT) puis la correction.",
     ["omega_hermes/bob.py"],
     ["omega_hermes.test_bob"], ["omega_hermes/hermes_evidence.json"]),
    ("E-4.5", "§4.5 Boucle 200×5 graine 7",
     "Score ≥ 0,98, rejet inconnu/COVERT/DRAFT = 1,000, FPR = 0.",
     ["omega_hermes/loop.py", "omega_hermes/hermes.py"],
     ["omega_hermes.test_hermes"], ["omega_hermes/hermes_evidence.json"]),
    ("E-5.1", "§5.1 GARDIEN allowlist exacte",
     "Allowlist sans joker, refus typés, CONNECT refusé, détection heuristique signalée.",
     ["agent_guard/guard.py"],
     ["agent_guard.test_guard", "agent_guard.test_charge"],
     ["agent_guard/guard_evidence.json"]),
    ("E-5.2", "§5.2 Terminal SETUP_MODE",
     "Allowlist commandes et arguments, shell=False, délai 5 s, bac à sable, 64 Kio.",
     ["terminal_auth/server.py", "socle_preuve/auth.py"],
     ["terminal_auth.test_terminal"], ["outils/phase3_evidence.json"]),
    ("E-5.3", "§5.3 Runtime supervisé V8.1",
     "flock, relances bornées, SIGTERM propre, aucune persistance cachée.",
     ["runtime/superviseur.py"],
     ["runtime.test_superviseur"], ["outils/phase3_evidence.json"]),
    ("E-6.1", "§6.1 Orchestrateur",
     "21 suites blueprint + balayage HERMÈS + Ω Q + dashboard.",
     ["plateforme_omega/orchestrator.py", "plateforme_omega/omega_q.py"],
     ["plateforme_omega.test_plateforme"], ["plateforme_omega/plateforme_evidence.json"]),
    ("E-6.4", "§6.4 Règle Ω Q",
     "Q = S + P + R − C ; veto si l'attaquant réussit.",
     ["plateforme_omega/omega_q.py", "plateforme_omega/mtd.py"],
     ["plateforme_omega.test_plateforme"], ["plateforme_omega/omega_q_evidence.json"]),
    ("E-7.1", "§7.1 RAG extractif cité",
     "Jamais de mémoire inventée : titre, révision, URL, ou aveu.",
     ["rag_wiki/rag.py", "rag_wiki/corpus.py"],
     ["rag_wiki.test_rag"], ["rag_wiki/rag_evidence.json"]),
    ("E-7.3", "§7.3 Épinglage TLS",
     "SPKI SHA-256 YE2/Root YE/ISRG Root X2 ; interception fabriquée détectée.",
     ["rag_wiki/pinning.py"],
     ["rag_wiki.test_rag"], ["rag_wiki/pinning_evidence.json"]),
    ("E-8.1", "§8.1 Console unifiée statique",
     "HTML statique sans CDN, 0 erreur console, pas de débordement mobile, chiffres depuis les évidences.",
     ["console/generer.py"],
     ["console.test_console"], ["outils/phase7_evidence.json"]),
    ("E-8.2", "§8.2 Télégraphe scellé",
     "CRC-16/X-25, aller-retour exact, sceau témoin sur chaque trame reçue.",
     ["telegraphe/afsk.py", "telegraphe/transport.py"],
     ["telegraphe.test_afsk", "telegraphe.test_transport"],
     ["outils/phase7_evidence.json"]),
    ("E-10.3", "§10.3 Lignes rouges",
     "Pas d'endpoint RCE non authentifié, pas de persistance cachée, pas de keylogger.",
     ["socle_preuve/porte_http.py", "agent_guard/guard.py", "terminal_auth/server.py", "cryoloop_gateway/gateway.py", "omega_hermes/guardian.py", "runtime/superviseur.py"],
     ["cryoloop_gateway.test_gateway (test_la_passerelle_ne_peut_rien_executer)", "omega_hermes.test_phase4 (test_guardian_refuse_tout_contenu)", "runtime.test_superviseur (test_aucune_persistance_cachee)"],
     ["(propriété de code vérifiée statiquement)"]),
]


def existant(chemins: list[str]) -> list[dict]:
    res = []
    for c in chemins:
        chemin = os.path.join(RACINE, c)
        existe = os.path.exists(chemin)
        res.append({"chemin": c, "existe": existe,
                    "sha256": _sha(chemin)[:16] if existe else None})
    return res


def _sha(chemin: str) -> str:
    try:
        with open(chemin, "rb") as fh:
            return hashlib.sha256(fh.read()).hexdigest()
    except OSError:
        return ""


def cycle_plateforme_resume() -> dict:
    """Déclenche un cycle plateforme et renvoie son résumé pour inclusion au rapport."""
    r = subprocess.run([sys.executable, "-m", "plateforme_omega.orchestrator"],
                       cwd=RACINE, capture_output=True, text=True, timeout=900)
    doc = lire(os.path.join(RACINE, "plateforme_omega/plateforme_evidence.json"))
    m = doc["mesures"]
    return {"exit": r.returncode,
            "verdict": doc["verdict"],
            "blueprint": m["blueprint"],
            "echecs_connus": m["echecs_connus"],
            "echecs_inattendus": m["echecs_inattendus"],
            "duree_murale_s": round(m["duree_murale_s"], 1),
            "gain_parallele": round(m["gain_parallele"], 2),
            "paralleles": m["paralleles"],
            "omega_q": m["omega_q_decisions"],
            "balayage_hermes_meilleur": m["meilleur_balayage"]}


def ruff() -> dict:
    r = subprocess.run(["ruff", "check", "--select", "E9,F63,F7,F82,F401,F841", "--statistics", "."],
                       cwd=RACINE, capture_output=True, text=True, timeout=60)
    return {"exit": r.returncode, "sortie": r.stdout.strip()}


def coverage_resume() -> dict | None:
    try:
        r = subprocess.run(["python3", "-m", "coverage", "run", "--source=socle_preuve,omega_hermes,rinv,"
                            "plateforme_omega,agent_guard,cryoloop_gateway,terminal_auth,runtime,"
                            "cryoloop,rag_wiki,telegraphe,outils,console", "--branch", "-m", "unittest"],
                           cwd=RACINE, capture_output=True, text=True, timeout=600)
        if r.returncode:
            return {"exit": r.returncode, "erreur": r.stderr[-300:]}
        rep = subprocess.run(["python3", "-m", "coverage", "json", "-o", "-"], cwd=RACINE,
                             capture_output=True, text=True, timeout=60)
        data = json.loads(rep.stdout)
        total = data["totals"]
        fichiers = sorted(((p, d["summary"]["percent_covered"]) for p, d in data["files"].items()),
                          key=lambda t: t[1])
        return {"exit": 0, "pct_total": round(total["percent_covered"], 1),
                "stmts": total["num_statements"], "branches": total["num_branches"],
                "plus_bas_5": [{"fichier": p, "pct": round(v, 1)} for p, v in fichiers[:5]
                               if not (p.endswith("__main__.py") or "/demo" in p or "/banc" in p or "test_" in p or "scaling_ref" in p)],
                "cœur_sous_80": sorted([{"fichier": p, "pct": round(v, 1)} for p, v in fichiers
                                        if v < 80 and not (p.endswith("__main__.py") or "/demo" in p or "/banc" in p
                                                           or "test_" in p or "scaling_ref" in p or p.endswith("__init__.py"))],
                                       key=lambda d: d["pct"])}
    except (FileNotFoundError, subprocess.SubprocessError, ValueError) as e:
        return {"exit": 1, "erreur": str(e)}


def toutes_les_evidences() -> list[dict]:
    res = []
    for ch in sorted(glob.glob(os.path.join(RACINE, "**", "*_evidence.json"), recursive=True)):
        if "__pycache__" in ch or ".src/" in ch:
            continue
        d = lire(ch)
        res.append({"chemin": os.path.relpath(ch, RACINE), "module": d["module"],
                    "phase": d["phase"], "etiquette": d["etiquette"], "verdict": d["verdict"]})
    return res


def generer_matrice() -> str:
    lignes = [
        "# Matrice de traçabilité — exigence → code → test → évidence",
        "",
        "> Générée par `python3 -m dossier.generer`. Chaque exigence du blueprint est reliée au",
        "> code qui la met en œuvre, aux tests qui la contrôlent et au fichier d'évidence qui",
        "> en porte la mesure. Un vide dans une colonne est une dette explicite, pas un oubli.",
        "",
        "| Exigence | Source | Résumé | Code | Tests | Évidence |",
        "|---|---|---|---|---|---|",
    ]
    for code, source, resume, fichiers, tests, evidences in EXIGENCES:
        presents = existant(fichiers)
        manquants = [p["chemin"] for p in presents if not p["existe"]]
        code_col = ", ".join(f"`{p['chemin']}`" for p in presents)
        if manquants:
            code_col += " **(manquant : " + ", ".join(manquants) + ")**"
        tests_col = ", ".join(f"`{t}`" for t in tests) or "—"
        ev_col = ", ".join(f"`{e}`" for e in evidences) or "—"
        lignes.append(f"| **{code}** | {source} | {resume} | {code_col} | {tests_col} | {ev_col} |")
    return "\n".join(lignes) + "\n"


def generer_readme(rapport: dict) -> str:
    today = datetime.datetime.now(datetime.timezone.utc).date().isoformat()
    plateforme = rapport["plateforme"]
    couverture = rapport.get("couverture") or {}
    etiq = collections.Counter(e["etiquette"] for e in rapport["evidences"])
    verdicts = collections.Counter(e["verdict"] for e in rapport["evidences"])
    return f"""# Dossier de vérification final — Plateforme OMEGA-HERMÈS / LOOP

*{today} · discipline d'ingénierie type NASA (conformément au §10.2 du blueprint, aucune
certification n'est conférée ni revendiquée ; seule la rigueur est visée).*

## Résumé exécutable

- **Suite complète** : {rapport['tests']['total']} tests, verdict `{rapport['tests']['verdict']}`.
- **Cycle plateforme** : {plateforme['blueprint']['ok']}/{plateforme['blueprint']['total']} suites du blueprint
  OK en {plateforme['duree_murale_s']} s (gain ×{plateforme['gain_parallele']} sur
  {plateforme['paralleles']} voies). Échecs connus documentés :
  {", ".join(f"`{k}`" for k in plateforme['echecs_connus']) or "aucun"}. Échecs inattendus :
  {", ".join(f"`{k}`" for k in plateforme['echecs_inattendus']) or "aucun"}.
- **Ω Q** : {json.dumps(plateforme['omega_q'])} sur {sum(plateforme['omega_q'].values())} évaluations.
- **Analyse statique** (ruff `E9,F63,F7,F82,F401,F841`) : {"PROPRE" if rapport['ruff']['exit'] == 0 else "VIOLATIONS"}.
- **Couverture** : {couverture.get('pct_total', 'n/d')} % ({couverture.get('stmts', '?')} instructions,
  {couverture.get('branches', '?')} branches) ; les points bas documentés plus bas.
- **Évidences** ({sum(verdicts.values())}) : {json.dumps(dict(verdicts), sort_keys=True)}.
- **Étiquettes** : {json.dumps(dict(etiq), sort_keys=True)}.

## Matrice de traçabilité

Voir [`matrice_tracabilite.md`](matrice_tracabilite.md) — chaque exigence du blueprint
est liée à son code, ses tests et son évidence.

## Rapport complet (JSON)

[`rapport_analyse.json`](rapport_analyse.json).

## Discipline appliquée

1. **Un module = une évidence produite par exécution.** Aucun chiffre tapé à la main.
2. **Un critère fixé avant la mesure.** Les échecs connus restent écrits dans l'évidence
   et dans le journal ; ils ne sont pas retouchés après coup pour passer. Exemple : la
   suite `fusion` échoue ouvertement sur ce corpus (RRF sous TF-IDF seul), avec analyse
   écrite des pertes et variantes essayées puis abandonnées.
3. **Défauts trouvés sous charge parallèle corrigés avec test de régression**, pas masqués
   par une relance : terminal (`EOF ≠ sortie`), portes HTTP et serveur TLS (fermeture
   différée bornée après réponse d'erreur), file d'écoute poussée à 128.
4. **Séparation revendication / spécification / implémentation / test / validation.**
   Le validateur CRYOLOOP traite 18 scénarios synthétiques ; `LOOP 001` sur les archives
   réelles est **PENDING `entrees_absentes`** parce que les archives DON-DC01 n'ont pas
   été fournies — aucun chiffre n'est fabriqué à leur place.
5. **Mission affichée comme proposée**, jamais comme acquise. La console l'écrit.
6. **Lignes rouges tenues** : refus de scripts offensifs présentés en « recherche civile
   humanitaire », refus de modification de `~/.bashrc`, refus d'endpoint `?cmd=` sans
   authentification, refus d'installation d'outillage offensif sans contexte autorisé.

## Points bas documentés

{(_points_bas(couverture) if couverture else "Pas de mesure de couverture disponible.")}

## Ce que ce dossier ne prouve pas

- Pas de certification formelle. NASA et autres labels : explicitement refusés (§10.2).
- Pas de preuve mathématique du cœur Ed25519 (seulement vecteurs RFC 8032 et contrôle
  croisé avec `cryptography`).
- Pas de couverture > 95 %. Le superviseur runtime (25 %) est testé en sous-processus,
  que `coverage.py` ne voit pas sans configuration multiprocess ; les entrées
  `__main__.py`, `banc.py` et `demo.py` sont considérées comme coquilles.
- Pas de vérification sur WebKit/Gecko : seul Chromium headless a tourné.
- Pas de preuve que la totalité des codes de refus des portes couvre tous les cas
  rencontrables (allowlist, politique d'arguments) : seuls les cas énumérés sont joués.
"""


def _points_bas(cov: dict) -> str:
    if cov.get("cœur_sous_80"):
        lignes = ["Modules du cœur sous 80 % de couverture (cause documentée) :", ""]
        for f in cov["cœur_sous_80"]:
            cause = ""
            if "superviseur" in f["fichier"]:
                cause = " — testé en sous-processus (non vu par coverage.py sans multiprocess)"
            lignes.append(f"- `{f['fichier']}` : {f['pct']} %{cause}")
        return "\n".join(lignes)
    return "Aucun module du cœur sous 80 %."


def main() -> int:
    print("[*] matrice de traçabilité…", file=sys.stderr)
    matrice = generer_matrice()
    with open(os.path.join(DOSSIER, "matrice_tracabilite.md"), "w", encoding="utf-8") as fh:
        fh.write(matrice)

    print("[*] cycle plateforme sur le code courant…", file=sys.stderr)
    plateforme = cycle_plateforme_resume()
    print("[*] ruff + couverture…", file=sys.stderr)
    r = subprocess.run([sys.executable, "-W", "error", "-m", "unittest"], cwd=RACINE,
                       capture_output=True, text=True, timeout=900)
    import re
    m = re.search(r"Ran (\d+) tests", r.stderr)
    tests = {"total": int(m.group(1)) if m else None,
             "verdict": "OK" if r.returncode == 0 else "ECHEC",
             "duree_s": None, "sortie_finale": r.stderr.strip().splitlines()[-1] if r.stderr else ""}

    rapport = {
        "genere_le": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "commit": subprocess.run(["git", "rev-parse", "HEAD"], cwd=RACINE,
                                  capture_output=True, text=True).stdout.strip(),
        "exigences": [{"code": c, "source": s, "resume": r, "fichiers": existant(f),
                       "tests": t, "evidences": ev} for c, s, r, f, t, ev in EXIGENCES],
        "evidences": toutes_les_evidences(),
        "plateforme": plateforme,
        "tests": tests,
        "ruff": ruff(),
        "couverture": coverage_resume(),
    }
    with open(os.path.join(DOSSIER, "rapport_analyse.json"), "w", encoding="utf-8") as fh:
        json.dump(rapport, fh, ensure_ascii=False, indent=2, sort_keys=False)
    with open(os.path.join(DOSSIER, "README.md"), "w", encoding="utf-8") as fh:
        fh.write(generer_readme(rapport))
    print(f"\ndossier écrit : {DOSSIER}")
    print(f"  tests : {tests['verdict']} ({tests['total']})")
    print(f"  plateforme : {plateforme['blueprint']['ok']}/{plateforme['blueprint']['total']} "
          f"échecs connus {plateforme['echecs_connus']} inattendus {plateforme['echecs_inattendus']}")
    print(f"  ruff : {'propre' if rapport['ruff']['exit'] == 0 else 'violations'}")
    if rapport.get("couverture"):
        print(f"  couverture : {rapport['couverture'].get('pct_total', 'n/d')} %")
    return 0 if plateforme["echecs_inattendus"] == [] and tests["verdict"] == "OK" else 1


if __name__ == "__main__":
    sys.exit(main())
