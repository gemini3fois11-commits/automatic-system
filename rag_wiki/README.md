# rag_wiki — connaissance — `[VÉRIFIÉ]`

## Rôle

La couche connaissance (blueprint §7) : répondre **à partir de sources citées, jamais de
mémoire inventée**. Corpus Wikipédia réel et tracé, recherche par trois stratégies
combinées, réponse extractive avec titre, révision et URL ; épinglage TLS des certificats
Let's Encrypt « Generation Y ».

| Fichier | Rôle |
|---|---|
| `corpus.py` | Collecte polie (un titre par requête, `retry-after` respecté) de 12 articles ; révision, URL et date gardées |
| `rag.py` | Découpage 500 / 100, TF-IDF avec boost du titre ×2, réponse extractive citée ou aveu `aucune_source_pertinente` |
| `fusion.py` | TF-IDF, BM25, entités/titres, fusion RRF k = 60 ; voie neuronale absente déclarée |
| `pinning.py` | Parseur DER en Python pur, épingles SHA-256 des SPKI de YE2, Root YE, ISRG Root X2 |

## Source des textes

- **Wikipédia en français** (`fr.wikipedia.org`), par l'**Action API**, un article par requête
  (`action=query`, `prop=extracts`, texte brut). Ce n'est pas Spécial:Exporter. Chiffres et dates
  sont conservés (un test le vérifie : chaque document contient des années à 4 chiffres).
- **Pas Wikidata.** Wikidata porte des faits structurés (entités, relations, SPARQL) ; utile pour un
  graphe de connaissances, pas pour le texte. Non utilisé ici.
- **Grande échelle, non utilisée ici** : le jeu Hugging Face `wikimedia/wikipedia`, config
  `20231101.fr` (2 564 646 articles, ~4,6 Go selon le propriétaire et le blueprint §7.2). Deux
  constats du propriétaire, non revérifiés dans ce dépôt : ses textes ont les chiffres et les dates
  effacés (« né le à Moulins »), et sa lecture ligne par ligne est bloquée (`/rows` → 502).
- **La source alimente la recherche, pas un entraînement.** Les « IA » du projet sont des agents à
  règles et un RAG lexical (TF-IDF, BM25, entités). Aucun modèle n'est entraîné sur ces textes.
  Nuance exacte : BOB est un petit classifieur statistique *ajusté* (moyennes et variances) sur des
  signaux synthétiques, et l'ELM de `hyper` un ajustement par moindres carrés ; aucun réseau de
  neurones entraîné, nulle part.

## Usage

```bash
python3 -m rag_wiki.rag "Qui a inventé le code Morse ?"
python3 -m rag_wiki.rag --eval        # rag_evidence.json
python3 -m rag_wiki.fusion --eval     # fusion_evidence.json
python3 -m rag_wiki.pinning --eval    # pinning_evidence.json
python3 -m rag_wiki.corpus            # recollecte le corpus (réseau requis)
```

## Tests

```bash
python3 -m unittest rag_wiki.test_rag     # sans réseau : corpus et certificats sont dans le dépôt
```

## Limites honnêtes

- **La fusion ne fait pas mieux que TF-IDF seul sur ce corpus** : la stratégie « entités » classe
  d'un bloc tous les morceaux d'un document cité dans la question. Le critère, fixé avant la
  mesure, échoue ; la suite `fusion` est en échec et le reste. Deux variantes ont été essayées
  puis abandonnées pour ne pas ajuster le système aux 8 questions (voir `fusion_evidence.json`).
- 8 questions fixées à l'avance : échantillon trop petit pour conclure sur la généralisation.
- La voie neuronale (`all-MiniLM-L6-v2`) n'est pas active : son téléchargement exige une
  instruction explicite du propriétaire.
- Épinglage : empreintes et chaînage des noms seulement, ni signatures, ni dates, ni révocation.
  Le contrôle live est une observation dépendante du réseau, pas un critère. Le blueprint attendait
  `PINNED_FAIL` derrière un proxy interceptant ; quand le live a pu être joué ici, le proxy laissait
  passer la vraie chaîne (`PINNED_OK`). La détection est prouvée sur une chaîne d'interception fabriquée.
- Licence : textes de Wikipédia sous **CC BY-SA 4.0**, contributeurs de Wikipédia, aux révisions
  indiquées dans `corpus.json`. Certificats publiés par Let's Encrypt / ISRG.
