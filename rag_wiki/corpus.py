"""Corpus Wikipédia EN FRANÇAIS (blueprint §7.1) : un titre par requête, débit poli, traçabilité.

Source : fr.wikipedia.org par l'Action API. Ce n'est ni Wikidata (faits structurés, SPARQL),
ni le jeu Hugging Face `wikimedia/wikipedia` config `20231101.fr` (voir README : non utilisé).
Le texte alimente la RECHERCHE du RAG ; aucun modèle n'est entraîné dessus.

Chaque document garde son titre, son URL, l'identifiant et la date de la révision lue,
et la date de collecte. Texte sous licence CC BY-SA 4.0 (Wikipédia) : l'attribution
est conservée dans corpus.json et rappelée dans le README.

  python3 -m rag_wiki.corpus        # (re)collecte et écrit rag_wiki/corpus.json
"""

import datetime
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

DOSSIER = os.path.dirname(os.path.abspath(__file__))
CORPUS = os.path.join(DOSSIER, "corpus.json")
API = "https://fr.wikipedia.org/w/api.php"
AGENT = "omega-hermes-rag/0.1 (demonstration locale)"   # générique : aucune donnée personnelle
TITRES = ("Terre", "Lune", "Soleil", "Mars (planète)", "Système solaire", "Cryptographie",
          "Fonction de hachage", "SHA-2", "Télégraphe électrique", "Code Morse international",
          "Filtre de Kalman", "Transformation de Fourier rapide")
PAUSE_S = 2.0
METHODE = ("Action API de Wikipédia en français, action=query, prop=extracts, explaintext, "
           "un titre par requête — pas Spécial:Exporter, pas le jeu Hugging Face, pas Wikidata")


def _get(params: dict, essais: int = 6) -> dict:
    url = API + "?" + urllib.parse.urlencode(params)
    for k in range(essais):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": AGENT}),
                                        timeout=30) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code not in (429, 503) or k == essais - 1:
                raise
            time.sleep(int(e.headers.get("retry-after", "30")) + 2 * (k + 1))
    raise RuntimeError("inaccessible")


def sans_latex(texte: str) -> str:
    """Retire les blocs « {\\displaystyle …} » en respectant l'appariement des accolades."""
    sortie, i = [], 0
    while True:
        j = texte.find("{\\displaystyle", i)
        if j < 0:
            sortie.append(texte[i:])
            return "".join(sortie)
        sortie.append(texte[i:j])
        profondeur, k = 0, j
        while k < len(texte):
            profondeur += {"{": 1, "}": -1}.get(texte[k], 0)
            k += 1
            if profondeur == 0:
                break
        i = k


def nettoyer(texte: str) -> str:
    """Réduit les titres « == … == » à leur libellé (piège du §7.1) et les débris de formules
    mathématiques (colonnes d'espaces et de symboles isolés) laissés par l'extraction en texte brut."""
    texte = re.sub(r"^=+\s*(.*?)\s*=+\s*$", r"\1.", sans_latex(texte), flags=re.M)
    lignes = [l.strip() for l in texte.split("\n")]
    lignes = [l for l in lignes if len(l) > 3 or not l]          # une ligne de 1 à 3 signes = débris de formule
    texte = "\n".join(lignes)
    texte = re.sub(r"[ \t]{2,}", " ", texte)
    return re.sub(r"\n{3,}", "\n\n", texte).strip()


def article(titre: str) -> dict:
    d = _get({"action": "query", "format": "json", "prop": "extracts|revisions|info", "explaintext": 1,
              "rvprop": "ids|timestamp", "inprop": "url", "titles": titre, "redirects": 1})
    page = next(iter(d["query"]["pages"].values()))
    if "missing" in page or not page.get("extract"):
        raise ValueError(f"article vide ou absent : {titre}")
    rev = page["revisions"][0]
    return {"titre": page["title"], "url": page["fullurl"], "revision": rev["revid"],
            "revision_date": rev["timestamp"], "texte": nettoyer(page["extract"])}


def collecter() -> dict:
    docs = []
    for i, t in enumerate(TITRES):
        if i:
            time.sleep(PAUSE_S)
        docs.append(article(t))
        print(f"  {docs[-1]['titre']} — révision {docs[-1]['revision']}, {len(docs[-1]['texte'])} caractères")
    return {"source": "fr.wikipedia.org", "methode": METHODE,
            "licence": "CC BY-SA 4.0 — contributeurs de Wikipédia",
            "collecte": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
            "documents": docs}


def charger() -> dict:
    with open(CORPUS, encoding="utf-8") as fh:
        return json.load(fh)


if __name__ == "__main__":
    c = collecter()
    with open(CORPUS, "w", encoding="utf-8") as fh:
        json.dump(c, fh, ensure_ascii=False, indent=1)
    print(f"{len(c['documents'])} documents écrits dans {CORPUS}")
    sys.exit(0)
