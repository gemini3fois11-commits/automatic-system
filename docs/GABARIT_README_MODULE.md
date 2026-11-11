# <nom du module> — `[ÉTIQUETTE]`

> Gabarit imposé par le blueprint (§0 phase 0, §11.4). Les quatre sections sont obligatoires.
> Aucun chiffre écrit à la main : citer le fichier `*_evidence.json` qui le contient.

## Rôle

Une phrase : ce que le module décide ou prouve, et comment il refuse.

## Usage

```bash
python3 -m <paquet>.<module> ...
```

Entrées, sorties, raisons de refus (identifiants stables, ex. `hote_non_autorise`).

## Tests

```bash
python3 -m unittest <paquet>.test_<module>
```

Évidence produite : `<paquet>/<module>_evidence.json` (graine 7 par défaut).

## Limites honnêtes

- Ce que le module ne fait pas.
- Ce qui est `[SIMULÉ]`, `[SPÉCIFIÉ]` ou `[EXPÉRIMENTAL]`.
- Dans quelles conditions ses garanties tombent.
