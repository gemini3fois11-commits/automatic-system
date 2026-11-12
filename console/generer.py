"""Console unifiée (blueprint §8.1) : lit TOUS les *_evidence.json et produit un HTML
statique auto-contenu. Aucun CDN, aucun serveur obligatoire. Les chiffres ne sont jamais
tapés à la main : ils viennent des évidences produites par exécution (§9.1).

  python3 -m console.generer         # écrit console/plateforme-omega-hermes-v1-0.html
"""

import collections
import glob
import html
import json
import os
import sys

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXCLUS = {".git", ".src", "__pycache__"}
ETIQUETTES = {"DÉMONTRÉ": "ok", "VÉRIFIÉ": "ok", "SIMULÉ": "mesure",
              "SPÉCIFIÉ": "ko", "EXPÉRIMENTAL": "mesure", "FICTION": "ko", "NON ÉTABLI": "ko"}


def evidences() -> list[dict]:
    docs = []
    for chemin in sorted(glob.glob(os.path.join(RACINE, "**", "*_evidence.json"), recursive=True)):
        if EXCLUS & set(os.path.relpath(chemin, RACINE).split(os.sep)):
            continue
        with open(chemin, encoding="utf-8") as fh:
            d = json.load(fh)
        d["_chemin"] = os.path.relpath(chemin, RACINE)
        docs.append(d)
    return docs


def ligne_critere(c: dict) -> str:
    etat = "ok" if c.get("ok") else "ko"
    detail = html.escape(c.get("detail") or "")
    nom = html.escape(c.get("critere") or c.get("controle") or c.get("cas") or c.get("scenario") or "")
    return f'<li class="{etat}"><span>{nom}</span>{f"<em>{detail}</em>" if detail else ""}</li>'


def critere_entries(mesures: dict) -> list[dict]:
    for cle in ("criteres", "controles", "cas", "scenarios"):
        valeur = mesures.get(cle)
        if isinstance(valeur, list) and valeur and isinstance(valeur[0], dict):
            return valeur
    return []


def kpi_ligne(d: dict) -> str:
    cat = ETIQUETTES.get(d["etiquette"], "ko")
    status = "ok" if d["verdict"] == "OK" else "ko"
    criteres = critere_entries(d["mesures"])
    reussis = sum(1 for c in criteres if c.get("ok"))
    prop = f"{reussis}/{len(criteres)}" if criteres else d["verdict"]
    etq = html.escape(d["etiquette"])
    return (f'<tr class="{status}"><td>Phase {d["phase"]}</td>'
            f'<td><code>{html.escape(d["module"])}</code></td>'
            f'<td><span class="pastille {cat}">[{etq}]</span></td>'
            f'<td class="chiffre">{prop}</td>'
            f'<td><small>{html.escape(d["execution"]["genere_le"])}</small></td>'
            f'<td><small><a href="{html.escape(d["_chemin"])}">évidence</a></small></td></tr>')


def bloc_module(d: dict) -> str:
    criteres = critere_entries(d["mesures"])
    liste = "\n".join(ligne_critere(c) for c in criteres)
    limites = "\n".join(f"<li>{html.escape(l)}</li>" for l in d.get("limites", []))
    etq = html.escape(d["etiquette"])
    classe = "ok" if d["verdict"] == "OK" else "ko"
    return (f'<section class="module {classe}" id="m-{html.escape(d["module"])}">'
            f'<h3><code>{html.escape(d["module"])}</code>'
            f'<span class="pastille {ETIQUETTES.get(d["etiquette"], "ko")}">[{etq}]</span>'
            f'<small> phase {d["phase"]} · verdict <strong>{d["verdict"]}</strong></small></h3>'
            f'<p class="src">Évidence : <a href="{html.escape(d["_chemin"])}"><code>{html.escape(d["_chemin"])}</code></a> '
            f'· générée {html.escape(d["execution"]["genere_le"])} · commit '
            f'<code>{html.escape((d["execution"].get("commit") or "")[:7])}</code></p>'
            f'<h4>Critères</h4><ul class="criteres">{liste or "<li>(aucun critère listé)</li>"}</ul>'
            f'<h4>Limites honnêtes</h4><ul>{limites or "<li>(aucune limite écrite — refuser cette évidence)</li>"}</ul>'
            f'</section>')


def generer() -> str:
    docs = evidences()
    try:
        with open(os.path.join(RACINE, "VERSION"), encoding="utf-8") as fh:
            version = fh.read().strip()
    except FileNotFoundError:
        version = "?"
    # Synthèse globale
    par_etiq = collections.Counter(d["etiquette"] for d in docs)
    verdict_total = "OK" if all(d["verdict"] == "OK" for d in docs) else "INCOMPLET"
    lignes_kpi = "\n".join(kpi_ligne(d) for d in docs)
    blocs = "\n".join(bloc_module(d) for d in docs)
    # Tableau résumé : pour chaque document dont les mesures contiennent une clé "echecs_connus",
    # on expose la liste pour que le lecteur voie *ce qui ne passe pas* sans chercher.
    plateforme = next((d for d in docs if d["module"] == "plateforme"), None)
    bandeau_plateforme = ""
    if plateforme:
        m = plateforme["mesures"]
        echecs_connus = m.get("echecs_connus", {})
        bandeau_plateforme = (
            f'<section class="bandeau"><h2>Cycle plateforme</h2>'
            f'<p><strong>{m["blueprint"]["ok"]}/{m["blueprint"]["total"]}</strong> '
            f'suites du blueprint OK · murale {m["duree_murale_s"]:.1f} s · '
            f'gain parallèle ×{m["gain_parallele"]:.2f} sur {m["paralleles"]} voies · '
            f'Ω Q {json.dumps(m["omega_q_decisions"])}</p>'
            f'<p>Échecs connus (documentés) : '
            + (', '.join(f'<code>{html.escape(k)}</code>' for k in echecs_connus) or 'aucun')
            + '. Échecs inattendus : '
            + (', '.join(f'<code>{html.escape(k)}</code>' for k in m["echecs_inattendus"]) or 'aucun')
            + '.</p></section>'
        )

    # Mission : affichée comme PROPOSÉE (§1.1), jamais comme acquise.
    page = f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Plateforme OMEGA-HERMÈS / LOOP — v{html.escape(version)}</title>
<style>
:root{{--fond:#faf9f6;--texte:#1a1a17;--doux:#6b6b64;--cadre:#dcdbd3;--ok:#1b7a3a;--ko:#b3261e;--mesure:#9a6b00;--accent:#1f5fbf;--panneau:#fff}}
@media (prefers-color-scheme:dark){{:root{{--fond:#141412;--texte:#ecece6;--doux:#9b9b93;--cadre:#2f2f29;--ok:#6fcf8f;--ko:#ff8a80;--mesure:#ffcc5f;--accent:#7aa7ff;--panneau:#1c1c18}}}}
*{{box-sizing:border-box}} html,body{{margin:0;padding:0}}
body{{background:var(--fond);color:var(--texte);font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif;padding:0 16px}}
main{{max-width:960px;margin:0 auto;padding:24px 0 48px}}
header,section{{margin:0 0 32px}} h1{{font-size:1.5rem;margin:0 0 4px}} h2{{font-size:1.15rem;border-bottom:1px solid var(--cadre);padding-bottom:4px;margin-top:40px}} h3{{font-size:1rem;margin:16px 0 8px}}
.note{{color:var(--doux)}} .mission{{background:var(--panneau);border-left:4px solid var(--accent);padding:12px 16px;margin:0 0 24px;border-radius:0 6px 6px 0}}
.mission p{{margin:0}} .mission small{{color:var(--doux)}}
table{{width:100%;border-collapse:collapse;margin:12px 0;table-layout:auto}} td,th{{border-bottom:1px solid var(--cadre);padding:6px 8px;text-align:left;vertical-align:top;font-size:0.95em;word-break:break-word;overflow-wrap:break-word}}
tr.ok td:first-child{{border-left:3px solid var(--ok)}} tr.ko td:first-child{{border-left:3px solid var(--ko)}}
.chiffre{{font-variant-numeric:tabular-nums}} .pastille{{display:inline-block;padding:1px 8px;border-radius:999px;font-size:0.75em;font-weight:600;margin-left:6px}}
.pastille.ok{{background:color-mix(in srgb,var(--ok) 20%,transparent);color:var(--ok)}} .pastille.ko{{background:color-mix(in srgb,var(--ko) 20%,transparent);color:var(--ko)}} .pastille.mesure{{background:color-mix(in srgb,var(--mesure) 25%,transparent);color:var(--mesure)}}
.module{{background:var(--panneau);padding:12px 16px;margin:0 0 16px;border-radius:6px;border:1px solid var(--cadre);overflow-wrap:break-word;word-wrap:break-word}} .module.ko{{border-left:4px solid var(--ko)}} .module.ok{{border-left:4px solid var(--ok)}}
.criteres{{margin:0;padding-left:1.2em}} .criteres li.ok::marker{{color:var(--ok)}} .criteres li.ko::marker{{color:var(--ko)}}
.criteres li.ok::before{{content:"✓ ";color:var(--ok);font-weight:700}} .criteres li.ko::before{{content:"✗ ";color:var(--ko);font-weight:700}}
.criteres li{{list-style:none}} .criteres em{{color:var(--doux);font-style:normal;margin-left:6px;font-size:0.9em;word-break:break-word;overflow-wrap:break-word;display:inline-block;vertical-align:top}}
code,.criteres span,a{{font-family:ui-monospace,monospace}} a{{color:var(--accent)}}
.bandeau{{background:var(--panneau);border:1px solid var(--cadre);border-radius:6px;padding:12px 16px}}
.limites li{{color:var(--doux)}}
nav ul{{list-style:none;padding:0;display:flex;flex-wrap:wrap;gap:6px}} nav li a{{text-decoration:none;padding:3px 8px;border:1px solid var(--cadre);border-radius:999px;font-size:0.85em}}
.src{{color:var(--doux);font-size:0.85em;margin:4px 0 8px;word-break:break-all}}
@media (max-width:640px){{main{{padding:16px 0 32px}} table{{font-size:0.9em}} nav ul li a{{font-size:0.8em}} .tableau{{overflow-x:auto;-webkit-overflow-scrolling:touch}} .tableau table{{min-width:0}}}}
</style>
</head>
<body>
<main>
<header>
  <h1>Plateforme OMEGA-HERMÈS / LOOP</h1>
  <p class="note">Version <code>{html.escape(version)}</code> · verdict global : <strong>{verdict_total}</strong> · {len(docs)} évidences lues</p>
  <aside class="mission">
    <p><strong>Mission — proposée, en attente de confirmation du propriétaire :</strong></p>
    <p>« Démontrer qu'un système défensif peut prouver son propre refus — et le prouver à un témoin indépendant. »</p>
    <small>Toute fonctionnalité qui ne sert pas cette phrase est hors périmètre, sauf outil d'appui explicitement listé (RAG, audit npm).</small>
  </aside>
</header>

{bandeau_plateforme}

<section>
  <h2>Toutes les évidences</h2>
  <p class="note">Étiquettes : {" · ".join(f'<span class="pastille {ETIQUETTES.get(e,"ko")}">[{html.escape(e)}] × {n}</span>' for e,n in sorted(par_etiq.items()))}.</p>
  <div class="tableau">
    <table>
      <thead><tr><th>Phase</th><th>Module</th><th>Étiquette</th><th>Critères</th><th>Générée le</th><th>Fichier</th></tr></thead>
      <tbody>{lignes_kpi}</tbody>
    </table>
  </div>
</section>

<section>
  <h2>Détail par module</h2>
  <nav><ul>{"".join(f'<li><a href="#m-{html.escape(d["module"])}"><code>{html.escape(d["module"])}</code></a></li>' for d in docs)}</ul></nav>
  {blocs}
</section>

<section>
  <h2>Ce que la plateforme ne fait pas</h2>
  <ul class="limites">
    <li>Pas d'endpoint d'exécution distante sans authentification (lignes rouges §10.3).</li>
    <li>Pas de persistance cachée (pas de modification de <code>~/.bashrc</code>, pas de démon auto-réinjecté).</li>
    <li>Pas de capture de frappes au niveau caractères. Seule alternative autorisée : <code>guardian</code> (catégories et timings seulement).</li>
    <li>Aucune certification (institutionnelle, NASA ou autre) n'est conférée ni revendiquée. La <strong>discipline</strong> d'ingénierie est l'objectif, le label ne l'est pas.</li>
  </ul>
</section>

<footer class="note"><p>Généré par <code>python3 -m console.generer</code>. Toute valeur affichée vient d'un fichier <code>*_evidence.json</code> produit par exécution. Aucun CDN, aucun compte, aucun serveur obligatoire.</p></footer>
</main>
</body>
</html>"""
    return page


def main() -> int:
    page = generer()
    chemin = os.path.join(os.path.dirname(os.path.abspath(__file__)), "plateforme-omega-hermes-v1-0.html")
    with open(chemin, "w", encoding="utf-8") as fh:
        fh.write(page)
    print(f"console générée : {chemin} · {len(page)} octets")
    return 0


if __name__ == "__main__":
    sys.exit(main())
