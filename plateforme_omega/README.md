# plateforme_omega — `[VÉRIFIÉ]`

## Rôle

La couche plateforme (blueprint §6) : un orchestrateur qui lance toutes les suites en
parallèle, mesure leur gain, balaie les réglages de HERMÈS, note chaque module avec Ω Q
et régénère un tableau de bord **depuis les évidences, jamais à la main**.

| Fichier | Rôle | Étiquette |
|---|---|---|
| `orchestrator.py` | 21 suites du blueprint + 9 ajoutées, balayage HERMÈS 6 configurations, Ω Q, tableau de bord | `[VÉRIFIÉ]` |
| `omega_q.py` | Q = S + P + R − C, veto si l'attaquant réussit | `[DÉMONTRÉ]` |
| `mtd.py` | 7 niveaux de cible mouvante ; rotation Ed25519 et HMAC réelles, attaquant modélisé | `[SIMULÉ]` |
| `watcher.py` | Sceaux SHA-256 et battements, sentinelle du veilleur, horloges injectées | `[VÉRIFIÉ]` |
| `rubik.py` | Cube 3×3 géométrique ; mélange de 200 coups défait par inversion | `[VÉRIFIÉ]` |
| `distribue.py` | Tâches sur de vrais processus, fautes « boom » et « silence » reprises | `[VÉRIFIÉ]` |
| `hyper.py` | 192 nombres → 10⁶ poids virtuels ; ELM virtuel contre ELM stocké | `[VÉRIFIÉ]` |
| `etoile.py` | *-algèbre des matrices complexes ; verdict = projection, sceau = conjugaison unitaire | `[DÉMONTRÉ]` |
| `codage.py` | Hamming (7,4) et entrelaceur : neutre sur bruit blanc, décisif sur rafales | `[SIMULÉ]` |
| `prng.py` + `prng/cryoloop_prng.cpp` | xoshiro256** en C++, vérifié au bit près et contre le vecteur publié de SplitMix64 | `[VÉRIFIÉ]` |
| `tls.py` | Journal TLS 1.3 durci ; saturation et clients muets = refus propre | `[VÉRIFIÉ]` |
| `agi.py` | Boucle d'agent `[SIMULATION] [SPÉCIFIÉ]` ; le mur en FLOPs est calculé | `[SIMULÉ]` |

## Usage

```bash
python3 -m plateforme_omega.orchestrator      # cycle complet → plateforme_evidence.json + plateforme_omega.html
python3 -m plateforme_omega.<module>          # une suite seule, écrit <module>_evidence.json
```

## Tests

```bash
python3 -m unittest plateforme_omega.test_plateforme     # rejoue un cycle complet
```

## Limites honnêtes

- Les suites `rag`, `pinning` et `fusion` sont **absentes** tant que la phase 6 n'est pas construite :
  l'orchestrateur les compte comme absentes, jamais comme réussies.
- Gain parallèle = somme des durées / durée murale, sur la machine indiquée dans l'évidence.
- Ω Q : S est la part de critères réussis de l'évidence de la suite ; P et R ne valent que si
  l'évidence mesure un gain ou une reprise, sinon 0 avec drapeau. Les poids viennent du blueprint
  et ne sont étalonnés sur aucun historique.
- MTD : le blueprint donne le niveau 1 comme meilleur Q. Ici, un attaquant qui vise une surface
  non tournée contourne toute rotation partielle ; les deux modèles d'attaquant diffèrent.
- Le flake `watcher` du blueprint n'existe pas ici (horloges injectées). En revanche, la charge
  parallèle a révélé un vrai bogue de concurrence dans le terminal, corrigé : voir son README.
