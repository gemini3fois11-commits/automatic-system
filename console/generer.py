"""Console unifiée v1.0 (blueprint §8.1) — rapport statique engendré depuis les évidences.

Un seul fichier HTML, cinq sections : HERMÈS, registre scellé, preuve, documentation
honnête, télégraphe. Règle d'or (§9.1) : aucun chiffre n'est tapé à la main ici ;
chaque nombre vient d'un `*_evidence.json` lu à la génération. Deux éléments sont
réellement interactifs et vérifiables dans le navigateur, sans rien inventer :

1. la vérification de la chaîne Γ (SHA-256 recalculé sur un journal réel scellé par
   `socle_preuve.gamma`, avec un bouton « falsifier ») ;
2. le manipulateur Morse adaptatif (port fidèle de `telegraphe.morse`).

Le témoin (HMAC/Ed25519) n'est pas rejoué dans la page : son secret reste hors du
navigateur. Son verdict est montré tel qu'enregistré, et dit comme tel.

Usage : python3 -m console.generer [--sortie console/console.html]
"""

import argparse
import html
import json
import os
import sys
import tempfile

from outils.evidence import lire
from socle_preuve.gamma import Chaine

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

EVIDENCES = {
    "hermes": "omega_hermes/hermes_evidence.json",
    "socle": "socle_preuve/preuve_evidence.json",
    "rinv": "rinv/systeme_evidence.json",
    "plateforme": "plateforme_omega/plateforme_evidence.json",
    "rag": "rag_wiki/rag_evidence.json",
    "fusion": "rag_wiki/fusion_evidence.json",
    "telegraphe": "telegraphe/telegraphe_evidence.json",
    "reception": "telegraphe/reception_evidence.json",
    "micro": "telegraphe/micro_evidence.json",
}


def charger() -> dict:
    return {nom: lire(os.path.join(RACINE, rel)) for nom, rel in EVIDENCES.items()}


def e(x) -> str:
    return html.escape(str(x))


def etiquette(doc: dict) -> str:
    return f"[{doc['etiquette']}]"


def chaine_echantillon() -> list[str]:
    """Scelle un petit journal Γ réel (données ASCII) et rend ses lignes JSONL."""
    with tempfile.TemporaryDirectory() as d:
        ch = Chaine(os.path.join(d, "demo.jsonl"))
        for msg, crc in [("SOS", "0x0ffb"), ("OMEGA HERMES", "0x097b"),
                         ("GRAINE 7", "0x9d0e"), ("CQ DE OMEGA", "0x5a3c")]:
            ch.inscrire("emission", "EMIS", "message_scelle",
                        {"message": msg, "crc_x25": crc})
        with open(ch.chemin, encoding="utf-8") as fh:
            return [l.rstrip("\n") for l in fh if l.strip()]


# ---------------------------------------------------------------- sections

def section_hermes(d: dict) -> str:
    m = d["hermes"]["mesures"]
    g = m["global"]
    lignes = "".join(
        f"<tr><td>{it['iteration']}</td><td>{it['score']:.4f}</td>"
        f"<td>{it['rejet_inconnu']:.3f}</td><td>{it['fpr']:.3f}</td>"
        f"<td>{it['ber']:.3f}</td></tr>" for it in m["iterations"])
    return f"""<section id="hermes"><h2>1 · HERMÈS <span class="etq">{e(etiquette(d['hermes']))}</span></h2>
<p class="note">Résultats enregistrés de la boucle (graine {e(d['hermes']['graine'])}),
données synthétiques. Ce n'est pas une boucle qui tourne dans le navigateur : les
mathématiques HERMÈS vivent dans <code>omega_hermes/</code> et ne sont pas réécrites
ici — on n'affiche que ce que Python a mesuré.</p>
<p><strong>Score global {g['score']:.4f}</strong> · rejet inconnu {g['rejet_inconnu']:.3f}
· FPR {g['fpr']:.3f} · BER {g['ber']:.3f} · exactitude 7 labels {g['exactitude_7_labels']:.3f}
· latence médiane {g['latence_mediane_ms']:.3f} ms</p>
<div class="tableau"><table><tr><th>Itération</th><th>Score</th><th>Rejet inconnu</th>
<th>FPR</th><th>BER</th></tr>{lignes}</table></div></section>"""


def section_registre(d: dict, lignes_chaine: list[str]) -> str:
    socle = d["socle"]["mesures"]
    rinv = d["rinv"]["mesures"]
    donnees_js = json.dumps(lignes_chaine)
    attaques = "".join(
        f"<li>{e(a['attaque'])} — audit local <code>exit {a['exit_local']}</code>, "
        f"témoin <code>exit {a['exit_temoin']}</code></li>"
        for a in rinv.get("attaques", []))
    return f"""<section id="registre"><h2>2 · Registre scellé
<span class="etq">{e(etiquette(d['socle']))}</span></h2>
<p>Chaque décision — refus compris — est inscrite dans une chaîne Γ (SHA-256 chaîné)
et scellée par un témoin indépendant. Réécrire un bloc <em>et</em> recalculer la suite
reproduit une chaîne localement cohérente ; seul le témoin le détecte.</p>
<p class="note">Socle : {socle['scenarios_reussis']}/{len(socle['scenarios'])} scénarios,
Ed25519 {socle['rfc8032']['reussis']}/{socle['rfc8032']['controles']} vecteurs RFC 8032.
rinv : {rinv['reussis']}/{len(rinv['controles'])} contrôles. Attaques rejouées :</p>
<ul class="attaques">{attaques}</ul>

<div class="widget"><h3>Vérifier la chaîne Γ, ici, dans votre navigateur</h3>
<p class="note">SHA-256 recalculé en direct sur un journal réellement scellé par
<code>socle_preuve.gamma</code>. Le témoin (HMAC/Ed25519) n'est <em>pas</em> rejoué :
son secret reste hors de la page. Son verdict enregistré est montré plus haut.</p>
<div class="boutons"><button id="btn-verifier">Vérifier</button>
<button id="btn-falsifier">Falsifier le bloc 2</button>
<button id="btn-restaurer">Restaurer</button></div>
<pre id="sortie-chaine" class="sortie"></pre></div>
<script>window.__CHAINE__ = {donnees_js};</script></section>"""


def section_preuve(d: dict) -> str:
    p = d["plateforme"]["mesures"]
    fu = d["fusion"]["mesures"]
    rag = d["rag"]["mesures"]
    oq = p["omega_q_decisions"]
    mb = p["meilleur_balayage"]
    strat = "".join(f"<tr><td>{e(k)}</td><td>{v:.3f}</td></tr>"
                    for k, v in fu["mrr_par_strategie"].items())
    return f"""<section id="preuve"><h2>3 · Preuve <span class="etq">{e(etiquette(d['plateforme']))}</span></h2>
<p><strong>{p['suites_ok']}/{p['suites_total']} suites OK</strong> · gain parallèle
×{p['gain_parallele']:.2f} · durée murale {p['duree_murale_s']:.1f} s · Ω Q :
ACCEPTER {oq['ACCEPTER']} / REVOIR {oq['REVOIR']} / REJETER {oq['REJETER']}.</p>
<p class="note">Meilleur balayage HERMÈS : facteur lâche {mb['facteur_lache']},
entraînement {mb['entrainement']}/classe → score {mb['score']:.4f},
rejet inconnu {mb['rejet_inconnu']:.3f}, FPR {mb['fpr']:.3f}.</p>
<p>Connaissance — RAG MRR <strong>{rag['mrr']:.3f}</strong> sur {rag['documents']} documents.</p>
<p class="echec">Échec assumé — fusion : MRR {fu['mrr_fusion']:.3f} <strong>sous</strong>
TF-IDF seul. Critère fixé avant la mesure, non retuné (étiquette {e(etiquette(d['fusion']))},
verdict {e(d['fusion']['verdict'])}). HF actif : {e(fu['hf_actif'])}.</p>
<div class="tableau"><table><tr><th>Stratégie</th><th>MRR</th></tr>{strat}</table></div></section>"""


def section_documentation(d: dict) -> str:
    return f"""<section id="doc"><h2>4 · Documentation honnête</h2>
<p><strong>Mission</strong> — proposée, en attente de confirmation du propriétaire :
<em>démontrer qu'un système défensif peut prouver son propre refus, et le prouver à un
témoin indépendant.</em></p>
<div class="deux"><div><h3>Ce que le système fait</h3><ul>
<li>Inscrit chaque décision, refus compris, dans une chaîne Γ scellée par un témoin.</li>
<li>Détecte toute réécriture d'un journal, bloc par bloc, même recalculée.</li>
<li>Transporte un message (Morse, AFSK Bell 202) et scelle chaque émission.</li>
<li>Refuse par défaut : hôtes hors allowlist, scripts d'installation, transitions non prouvées.</li>
</ul></div><div><h3>Ce qu'il ne fait pas</h3><ul>
<li>Protéger contre qui tient la machine : secret et journal y vivent ensemble (§3.2).</li>
<li>Promettre la voie microphone du télégraphe : <span class="etq">[EXPÉRIMENTAL]</span>, non vérifiée.</li>
<li>Faire tourner HERMÈS dans le navigateur : la boucle est en Python, pas réécrite ici.</li>
<li>Se présenter comme une certification : c'est une démonstration défensive (§1.5, §10.2).</li>
</ul></div></div>
<p class="note">Étiquettes d'honnêteté employées partout : [DÉMONTRÉ], [VÉRIFIÉ], [SIMULÉ],
[SPÉCIFIÉ], [EXPÉRIMENTAL]. Un chiffre sans évidence devient une limite écrite, pas un nombre.</p></section>"""


def section_telegraphe(d: dict) -> str:
    m = d["telegraphe"]["mesures"]
    a, c, mo, r = m["afsk"], m["corruption"], m["morse"], m["registre"]
    return f"""<section id="telegraphe"><h2>5 · Télégraphe <span class="etq">{e(etiquette(d['telegraphe']))}</span>
<span class="note">(composant, pas la page d'accueil)</span></h2>
<p>AFSK Bell 202 — mark {a['mark_hz']} Hz / space {a['space_hz']} Hz, {a['baud']} bauds,
{a['fs']} Hz. Message de référence : {a['octets']} octets → {a['bits']} bits →
{a['echantillons']} échantillons ({a['duree_ms']:.0f} ms), CRC {e(a['crc_x25'])}.
Aller-retour exact en mémoire et via WAV ({a['wav_octets']} octets).</p>
<p class="note">Corruption : {c['octets_faux_livres']} octet faux livré sur {c['essais']} essais
({c['rejets']} rejets nets). Morse adaptatif : {mo['gigue_exacts']}/{mo['gigue_total']} exacts
sous gigue ±{mo['gigue_pct']} %. Émissions scellées : {r['emissions']}, témoin en accord ;
réécriture recalculée détectée (<code>{e(r['raison'])}</code>).</p>
<p class="note">Positionnement (§8.2) : Morse (1844), radio (1901), Bell 202 (1976) sont
anciens. Le seul apport revendiqué est le <strong>sceau vérifiable par un témoin</strong>.</p>
<p class="note">Voie microphone <span class="etq">{e(etiquette(d['micro']))}</span> : récepteur à
synchronisation aveugle, vérifié <strong>seulement</strong> sur boucle locale dégradée
synthétiquement — plancher 100 % à {e(d['micro']['mesures']['snr_plancher_100pct_db'])} dB,
{d['micro']['mesures']['faux_positifs']['faux']} faux positif sur
{d['micro']['mesures']['faux_positifs']['essais']} essais de bruit pur. Aucun canal
acoustique réel ; rien n'est promis sur une vraie transmission par le son.</p>

<div class="widget"><h3>Manipulateur Morse — maintenez la barre Espace (ou le bouton)</h3>
<p class="note">Décodeur à unité de temps <em>adaptative</em> : l'unité est estimée depuis
votre cadence, jamais donnée. Port fidèle de <code>telegraphe.morse</code>.</p>
<div class="boutons"><button id="btn-key" type="button">● Appuyer (Espace)</button>
<button id="btn-rejouer" type="button">Rejouer « CQ DE OMEGA HERMES »</button>
<button id="btn-vider" type="button">Vider</button></div>
<p>Signal : <code id="morse-signal"></code></p>
<p>Décodé : <strong id="morse-texte"></strong></p></div>
{_sous_section_reception(d)}</section>"""


def _sous_section_reception(d: dict) -> str:
    rc = d["reception"]["mesures"]
    v = rc["verdicts"]
    lignes = "".join(
        f"<tr><td>{e(s['scenario'])}</td>"
        f"<td class=\"{'ok' if s['decision']=='ACCEPTE' else 'echec' if s['decision']=='REFUSE' else ''}\">"
        f"{e(s['decision'])}</td><td><code>{e(s['raison'])}</code></td></tr>"
        for s in rc["scenarios"])
    r = rc["reecriture"]
    return f"""<div class="widget"><h3>Le télégraphe qui refuse
<span class="etq">{e(etiquette(d['reception']))}</span></h3>
<p class="note">Doctrine BOB appliquée à la réception (§8.2) : deux portes (CRC, puis
émetteur allowlisté + HMAC non rejoué), trois verdicts. L'inconnu est mis en
<strong>quarantaine avec raison écrite</strong>, jamais livré en silence ; chaque verdict
est scellé dans une chaîne Γ témoignée. Résultats enregistrés, graine {e(d['reception']['graine'])}.</p>
<p>ACCEPTE {v['ACCEPTE']} · QUARANTAINE {v['QUARANTAINE']} · REFUSE {v['REFUSE']} ·
{rc['sceau']['blocs']} verdicts scellés, témoin en accord ·
réécriture d'un verdict détectée (<code>{e(r['raison'])}</code>).</p>
<div class="tableau"><table><tr><th>Scénario reçu</th><th>Verdict</th><th>Raison</th></tr>
{lignes}</table></div></div>"""


# ---------------------------------------------------------------- script

SCRIPT = r"""
<script>
const GENESE = "0".repeat(64);
function canonical(o){
  if(Array.isArray(o)) return "["+o.map(canonical).join(",")+"]";
  if(o && typeof o === "object"){
    return "{"+Object.keys(o).sort().map(k=>JSON.stringify(k)+":"+canonical(o[k])).join(",")+"}";
  }
  return JSON.stringify(o);
}
function octets(prevAscii, canonStr){
  const enc = new TextEncoder();
  const a = enc.encode(prevAscii), b = enc.encode(canonStr);
  const out = new Uint8Array(a.length + b.length);
  out.set(a, 0); out.set(b, a.length); return out;
}
async function sha256Hex(bytes){
  const d = await crypto.subtle.digest("SHA-256", bytes);
  return [...new Uint8Array(d)].map(x=>x.toString(16).padStart(2,"0")).join("");
}
async function verifierChaine(lignes){
  let prev = GENESE;
  for(let i=0;i<lignes.length;i++){
    let bloc; try { bloc = JSON.parse(lignes[i]); } catch(_) { return {integre:false, seq:i, raison:"json_invalide"}; }
    const corps = {}; for(const k of Object.keys(bloc)) if(k!=="hash") corps[k]=bloc[k];
    if(bloc.prev_hash !== prev) return {integre:false, seq:bloc.seq, raison:"prev_hash_rompu"};
    const h = await sha256Hex(octets(bloc.prev_hash, canonical(corps)));
    if(h !== bloc.hash) return {integre:false, seq:bloc.seq, raison:"hash_invalide"};
    prev = bloc.hash;
  }
  return {integre:true, blocs:lignes.length, tete:prev};
}
window.verifierChaine = verifierChaine; window.canonical = canonical;

(function(){
  let lignes = (window.__CHAINE__||[]).slice();
  const original = lignes.slice();
  const sortie = document.getElementById("sortie-chaine");
  async function montrer(){
    const r = await verifierChaine(lignes);
    sortie.className = "sortie " + (r.integre ? "ok" : "echec");
    sortie.textContent = r.integre
      ? `INTÈGRE — ${r.blocs} bloc(s), tête ${r.tete.slice(0,16)}…`
      : `ROMPUE — seq ${r.seq} : ${r.raison}`;
  }
  const b = id => document.getElementById(id);
  if(b("btn-verifier")){
    b("btn-verifier").onclick = montrer;
    b("btn-falsifier").onclick = () => {
      if(lignes.length < 2) return;
      const o = JSON.parse(lignes[1]);
      o.donnees = Object.assign({}, o.donnees, {message:"FALSIFIE"});
      lignes[1] = JSON.stringify(o); montrer();
    };
    b("btn-restaurer").onclick = () => { lignes = original.slice(); montrer(); };
    montrer();
  }
})();

// ---- Morse (port fidèle de telegraphe.morse) ----
const MORSE = {A:".-",B:"-...",C:"-.-.",D:"-..",E:".",F:"..-.",G:"--.",H:"....",I:"..",
J:".---",K:"-.-",L:".-..",M:"--",N:"-.",O:"---",P:".--.",Q:"--.-",R:".-.",S:"...",T:"-",
U:"..-",V:"...-",W:".--",X:"-..-",Y:"-.--",Z:"--..","0":"-----","1":".----","2":"..---",
"3":"...--","4":"....-","5":".....","6":"-....","7":"--...","8":"---..","9":"----.",
".":".-.-.-",",":"--..--","?":"..--..","/":"-..-."};
const INV = Object.fromEntries(Object.entries(MORSE).map(([k,v])=>[v,k]));
function morseEncode(t){
  return t.toUpperCase().trim().split(/\s+/).map(mot =>
    [...mot].map(c => { if(!(c in MORSE)) throw "caractere_hors_code:"+c; return MORSE[c]; }).join(" ")
  ).join(" / ");
}
function estimerUnite(durees){
  const s = [...durees].sort((a,b)=>a-b);
  let g = [s[0]];
  for(let i=0;i<s.length-1;i++){ if(s[i+1]-s[i] > 0.6*s[i]) break; g.push(s[i+1]); }
  return g.reduce((a,b)=>a+b,0)/g.length;
}
function morseDecode(ev){
  const sons = ev.filter(x=>x[0]===1);
  if(!sons.length) throw "aucun_son";
  const u = estimerUnite(ev.map(x=>x[1]));
  let sy = [], cur = [];
  for(const [etat,duree] of ev){
    if(etat===1) cur.push(duree >= 2*u ? "-" : ".");
    else if(duree >= 5*u){ sy.push(cur.join("")); cur=[]; sy.push("/"); }
    else if(duree >= 2*u){ sy.push(cur.join("")); cur=[]; }
  }
  sy.push(cur.join(""));
  let mots = [], mot = [];
  for(const p of sy){ if(p==="/"){ mots.push(mot.join(" ")); mot=[]; } else if(p) mot.push(p); }
  if(mot.length) mots.push(mot.join(" "));
  return mots.filter(m=>m).map(mot =>
    mot.split(" ").map(s => { if(!(s in INV)) throw "symbole_inconnu:"+s; return INV[s]; }).join("")
  ).join(" ");
}
window.morseEncode = morseEncode; window.morseDecode = morseDecode;
function dureesDepuisTexte(t, unite){
  const ev = [];
  morseEncode(t).split(" / ").forEach((mot,mi)=>{
    if(mi>0) ev.push([0,7*unite]);
    mot.split(" ").forEach((sym,li)=>{
      if(li>0) ev.push([0,3*unite]);
      [...sym].forEach((sg,si)=>{ if(si>0) ev.push([0,unite]); ev.push([1,(sg==="-"?3:1)*unite]); });
    });
  });
  return ev;
}
(function(){
  const sig = document.getElementById("morse-signal"), txt = document.getElementById("morse-texte");
  if(!sig) return;
  let ev = [], tDown = null, tUp = null;
  function rendre(){
    sig.textContent = ev.map(x=>x[0]===1 ? "▇".repeat(Math.max(1,Math.round(x[1]/80))) : " ".repeat(Math.max(1,Math.round(x[1]/80)))).join("");
    try { txt.textContent = morseDecode(ev) || "—"; } catch(err){ txt.textContent = "("+err+")"; }
  }
  function down(){ const now=performance.now(); if(tUp!==null) ev.push([0, now-tUp]); tDown=now; }
  function up(){ const now=performance.now(); if(tDown!==null) ev.push([1, now-tDown]); tUp=now; rendre(); }
  const btn = document.getElementById("btn-key");
  btn.addEventListener("mousedown", down); btn.addEventListener("mouseup", up);
  btn.addEventListener("touchstart", ev2=>{ev2.preventDefault();down();}, {passive:false});
  btn.addEventListener("touchend", ev2=>{ev2.preventDefault();up();}, {passive:false});
  let espace=false;
  document.addEventListener("keydown", ev2=>{ if(ev2.code==="Space" && !espace){ espace=true; ev2.preventDefault(); down(); }});
  document.addEventListener("keyup", ev2=>{ if(ev2.code==="Space"){ espace=false; ev2.preventDefault(); up(); }});
  document.getElementById("btn-vider").onclick = ()=>{ ev=[]; tDown=tUp=null; rendre(); };
  document.getElementById("btn-rejouer").onclick = ()=>{ ev = dureesDepuisTexte("CQ DE OMEGA HERMES", 120); tDown=tUp=null; rendre(); };
})();
</script>"""

CSS = """
:root{--fond:#f7f7f5;--texte:#1d1d1b;--doux:#6b6b66;--cadre:#ddd;--accent:#1b5e9c;
--ok:#1b7a3a;--ko:#b3261e;--boite:#fff}
@media (prefers-color-scheme:dark){:root{--fond:#151514;--texte:#ecece8;--doux:#a0a09a;
--cadre:#333;--accent:#6db3f2;--ok:#6fcf8f;--ko:#ff8a80;--boite:#1d1d1b}}
*{box-sizing:border-box}
body{margin:0;background:var(--fond);color:var(--texte);font:15px/1.6 system-ui,sans-serif}
main{max-width:860px;margin:0 auto;padding:24px 16px}
h1{font-size:1.5rem;margin:0 0 4px}h2{font-size:1.15rem;border-bottom:2px solid var(--accent);
padding-bottom:4px;margin-top:40px}h3{font-size:1rem;margin:16px 0 6px}
a{color:var(--accent)}code{font-family:ui-monospace,monospace;font-size:.92em}
.etq{color:var(--accent);font-weight:600;font-size:.85rem}
.note{color:var(--doux)}.ok{color:var(--ok)}.echec{color:var(--ko)}
table{width:100%;border-collapse:collapse;margin:8px 0}
td,th{border-bottom:1px solid var(--cadre);padding:5px 8px;text-align:left}
.tableau{overflow-x:auto}
.widget{background:var(--boite);border:1px solid var(--cadre);border-radius:8px;padding:14px 16px;margin:16px 0}
.boutons{display:flex;gap:8px;flex-wrap:wrap;margin:10px 0}
button{font:inherit;padding:7px 14px;border:1px solid var(--accent);background:transparent;
color:var(--accent);border-radius:6px;cursor:pointer}button:hover{background:var(--accent);color:var(--fond)}
.sortie{font-family:ui-monospace,monospace;padding:10px;border-radius:6px;border:1px solid var(--cadre);
white-space:pre-wrap;min-height:1.2em}.sortie.ok{border-color:var(--ok)}.sortie.echec{border-color:var(--ko)}
.deux{display:grid;grid-template-columns:1fr 1fr;gap:20px}
@media (max-width:620px){.deux{grid-template-columns:1fr}}
ul.attaques{font-size:.92rem;color:var(--doux)}nav{font-size:.9rem;margin:12px 0}nav a{margin-right:12px}
.pied{margin-top:40px;color:var(--doux);font-size:.88rem;border-top:1px solid var(--cadre);padding-top:12px}
"""


def rendre(d: dict, lignes_chaine: list[str]) -> str:
    gen = d["plateforme"]["execution"]["genere_le"]
    corps = (section_hermes(d) + section_registre(d, lignes_chaine) + section_preuve(d)
             + section_documentation(d) + section_telegraphe(d))
    return f"""<!doctype html><html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Console OMEGA-HERMÈS</title><style>{CSS}</style></head><body><main>
<h1>Console OMEGA-HERMÈS / LOOP</h1>
<p class="note">Rapport statique engendré depuis les fichiers d'évidence — aucun chiffre
saisi à la main (blueprint §8.1, §9.1). Deux éléments sont vérifiés en direct dans votre
navigateur : la chaîne Γ et le manipulateur Morse.</p>
<nav><a href="#hermes">HERMÈS</a><a href="#registre">Registre</a><a href="#preuve">Preuve</a>
<a href="#doc">Documentation</a><a href="#telegraphe">Télégraphe</a></nav>
{corps}
<p class="pied">Évidences lues : {e(', '.join(sorted(EVIDENCES.values())))}.
Dernier cycle plateforme : {e(gen)}.</p>
</main>{SCRIPT}</body></html>"""


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python3 -m console.generer")
    ap.add_argument("--sortie", default=os.path.join(RACINE, "console", "console.html"))
    a = ap.parse_args(argv)
    d = charger()
    page = rendre(d, chaine_echantillon())
    with open(a.sortie, "w", encoding="utf-8") as fh:
        fh.write(page)
    print(f"Console engendrée : {os.path.relpath(a.sortie, RACINE)} ({len(page)} octets, "
          f"{len(EVIDENCES)} évidences)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
