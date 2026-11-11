# runtime — runtime supervisé V8.1 — `[VÉRIFIÉ]`

## Rôle

Faire tourner un service du projet sans surprise (blueprint §5.3) : un seul superviseur
à la fois, relances bornées, arrêt propre, registre atomique, identité des processus
vérifiée avant tout signal, journal Γ. Aucune persistance cachée.

## Usage

```bash
python3 -m runtime.superviseur --etat runtime/etat -- python3 -m agent_guard.guard
```

Codes de sortie : `0` arrêt propre ou service terminé normalement · `1` relances épuisées ·
`2` un superviseur tient déjà le verrou. Journal : `DEMARRAGE`, `SORTIE`, `RELANCE`
(`attente_s` 1, 2, 4, 8, 8), `ABANDON`, `ARRET`, `REGISTRE` (`orphelin_termine`,
`pid_recycle_ignore`).

## Tests

```bash
python3 -m unittest runtime.test_superviseur
```

## Limites honnêtes

- Battement et registre locaux ne sont **pas** un consensus distribué : toute affirmation
  distribuée faite à partir de ce module serait `[SIMULÉ]`.
- Le superviseur ne se relance pas lui-même et rien ne le démarre au boot : c'est voulu
  (pas de persistance cachée). Le démarrage reste une décision du propriétaire.
- Le keepalive de 15 minutes évoqué au §5.2 n'est pas implémenté : il est marqué
  « provisoire, sans accord explicite du propriétaire ».
