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

- **Un échec connu : `fusion`.** Sur le corpus de ce dépôt, la fusion RRF fait moins bien que TF-IDF
  seul ; le critère, fixé avant la mesure, échoue et n'a pas été retouché. L'orchestrateur le liste
  dans `echecs_connus` avec sa raison ; tout autre échec est « inattendu » et fait échouer le cycle.
  Critère du blueprint : au moins 20 suites sur 21, le seul échec toléré étant documenté.
- Une suite dont le module n'existe pas est comptée **absente**, jamais réussie.
- Gain parallèle = somme des durées / durée murale, sur la machine indiquée dans l'évidence.
- Ω Q : S est la part de critères réussis de l'évidence de la suite ; P et R ne valent que si
  l'évidence mesure un gain ou une reprise, sinon 0 avec drapeau. Les poids viennent du blueprint
  et ne sont étalonnés sur aucun historique.
- MTD : le blueprint donne le niveau 1 comme meilleur Q. Ici, un attaquant qui vise une surface
  non tournée contourne toute rotation partielle ; les deux modèles d'attaquant diffèrent.
- Le flake `watcher` du blueprint n'existe pas ici (horloges injectées). En revanche, la charge
  parallèle a révélé **trois vrais défauts**, tous corrigés et couverts par des tests de régression
  plutôt que masqués par une relance :
  1. terminal — une commande ayant fermé sa sortie sans être encore sortie était tuée ;
  2. portes HTTP et serveur TLS — une erreur renvoyée sans lire le corps de la requête se
     transformait en connexion coupée côté client (RST du noyau) ; fermeture différée bornée ;
  3. portes HTTP — file d'écoute de 5 connexions, débordée par une rafale locale ; portée à 128.
- La suite `pinning` ne fait plus dépendre son verdict du réseau : le contrôle live est une observation.
