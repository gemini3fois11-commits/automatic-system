# omega_hermes — `[SIMULÉ]`

## Rôle

Cœur HERMÈS (blueprint §4) : un jumeau numérique produit des signaux
synthétiques, ALICE les perturbe ou les remplace par l'inconnu et des canaux
cachés, EYES les fusionne en 31 traits, BOB décide avec deux seuils, HERMÈS
mesure, et la boucle ajuste le seuil de BOB en journalisant chaque ajustement
dans une chaîne Γ du socle de preuve. L'indicateur critique est le **taux de
rejet de l'inconnu**, pas la reconnaissance du normal.

| Fichier | Rôle |
|---|---|
| `twin.py` | 5 modalités × 256 échantillons, 3 régimes (`REPOS`, `CHARGE`, `RESONANCE`) ; un flux aléatoire neuf par observation |
| `alice.py` | Bruit, jitter, dérive (gardent la classe) ; écrêtage, dropout (→ `ARTIFACT`) ; chirp, carré (→ `UNKNOWN`) ; `COVERT`, `DRAFT` |
| `eyes.py` | 6 descripteurs par modalité + corrélation temporel × électrique = 31 traits ; FFT radix-2 écrite à la main |
| `bob.py` | Plateaux d'abord, Mahalanobis diagonale, seuil strict = p99, seuil lâche = 100 × strict ; règle historique `seuil_unique` conservée |
| `hermes.py` | BER, FPR, FNR, rejets, rappel / précision par label, score et ses composantes |
| `loop.py` | Boucle 200 × 5, ajustements journalisés, évidence |
| `decouplage.py` | Vérification statique : le banc n'importe qu'une liste blanche et n'ouvre rien |

### Phase 4

| Fichier | Rôle |
|---|---|
| `swarm.py` | Essaim de 8 nœuds, battement de 5 s simulé : latence de détection, messages cachés, ampleur, fausses alarmes ; balayage de 4 niveaux de compromission |
| `reverie.py` | RESPIRE / DORT / RÊVE / CHOISI : 5 familles de rêves jugées par BOB, élection reproductible |
| `ai_mode.py` | Agents ACCEPTER / SIGNALER / QUARANTAINE avec hypothèse écrite et journalisée |
| `evasion.py` | 960 cas : un attaquant baisse l'amplitude de son canal caché ; courbe et plancher de détection |
| `attrape.py` | Chaque rejet mis en quarantaine avec un motif chiffré dans une chaîne Γ |
| `brouillons.py` | DRAFT isolé : rejet, puis distinction DRAFT / COVERT par le trait 31 |
| `guardian.py` | Dynamique de frappe par catégories et timings ; **les caractères sont refusés à l'entrée** |

Leçon mesurée en phase 4 : une première politique d'agent « plateaux → SIGNALER » envoyait
les ondes carrées étrangères en « capteur défaillant ». C'est le piège du §4.3 qui revient au
niveau de l'agent ; la décision UNKNOWN de BOB prime désormais sur l'indice de plateau.

## Usage

```bash
python3 -m omega_hermes.loop                       # graine 7, 200 × 5, 150 par classe
python3 -m omega_hermes.loop --graine 8 --journal ajustements.jsonl
python3 -m omega_hermes.phase4                     # 7 modules, 7 évidences
```

Décisions : une classe connue, `ARTIFACT` ou `UNKNOWN`. Ajustements journalisés :
`RESSERRE` (`anomalies_acceptees`), `RELACHE` (`connus_rejetes`), `MAINTIENT`
(`dans_la_cible`).

## Tests

```bash
python3 -m unittest omega_hermes.test_twin omega_hermes.test_eyes omega_hermes.test_bob omega_hermes.test_hermes omega_hermes.test_phase4
```

`test_bob` reproduit d'abord le défaut historique (seuil unique : une onde
carrée étrangère sort `ARTIFACT`), puis vérifie la correction (`UNKNOWN`).
`test_hermes` rejoue la commande de vérification complète de la phase 2.
Évidence produite : `omega_hermes/hermes_evidence.json` — tous les chiffres sont là,
aucun n'est recopié ici.

## Limites honnêtes

- **`[SIMULÉ]`** : données synthétiques uniquement. Rien ici ne prouve quoi que ce
  soit sur un signal réel.
- Les paramètres du jumeau et d'ALICE (amplitudes, variations, force des
  perturbations douces, largeur des chirps) ont été **réglés** pour que les
  familles soient séparables. BOB est mesuré sur ce monde-là. Les seuils, eux,
  n'ont pas été réglés : ce sont ceux du §4.3.
- **Deux interprétations du blueprint, à confirmer** : FPR = anomalie acceptée
  comme classe connue (« positif » = accepté) ; « entraînement 150 » = 150
  échantillons **par classe**. Avec 50 par classe, les connus sont rejetés
  plus souvent que prévu (distances d'entraînement biaisées vers le bas).
- `COVERT` et `DRAFT` sont rejetés, jamais nommés. L'exactitude sur 7 labels
  chute donc mécaniquement ; ce n'est pas une régression (§4.4).
- La boucle s'ajuste avec les labels d'ALICE : c'est un banc d'essai, pas un
  apprentissage en ligne.
- Les bandes de distance mesurées ne sont pas celles du blueprint (§4.3) : le
  jumeau n'est pas le même. Les ordres de grandeur sont dans l'évidence.
- La latence est mesurée par décision isolée, traits compris, en Python pur + numpy.
- Ω Q n'est pas encore calculé (phase 5) : au sens du §11.4, le module n'est pas « terminé ».
