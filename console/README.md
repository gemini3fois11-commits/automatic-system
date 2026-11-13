# console — console unifiée v1.0 — `[VÉRIFIÉ]`

## Rôle

Engendre un rapport HTML statique en une page (blueprint §8.1) à partir des
fichiers d'évidence du dépôt. Cinq sections : HERMÈS, registre scellé, preuve,
documentation honnête, télégraphe. Règle d'or (§9.1) : **aucun chiffre tapé à la
main** — chaque nombre est lu dans un `*_evidence.json` au moment de la génération.

Deux éléments sont réellement interactifs et vérifiés en direct dans le navigateur,
sans rien inventer :

- **Vérification de la chaîne Γ** : SHA-256 recalculé sur un journal réellement
  scellé par `socle_preuve.gamma`, avec un bouton « falsifier ». Le témoin
  (HMAC/Ed25519) n'est pas rejoué dans la page — son secret reste hors du
  navigateur — et son verdict enregistré est montré comme tel.
- **Manipulateur Morse adaptatif** : port fidèle de `telegraphe.morse` (barre
  Espace ou bouton, unité de temps estimée depuis la cadence).

## Usage

```bash
python3 -m console.generer                 # écrit console/console.html
python3 -m unittest console.test_generer
```

Ouvrir ensuite `console/console.html` dans un navigateur.

## Tests

```bash
python3 -m unittest console.test_generer
```

Le test vérifie que les cinq sections sont présentes, qu'aucun gabarit n'est laissé
non rempli, et que la chaîne Γ d'exemple embarquée est une vraie chaîne intègre
(relecture par `socle_preuve.gamma`). La fidélité des deux éléments interactifs est
vérifiée en Chromium sans tête (SHA-256 du navigateur égal à celui de Python, zéro
erreur console, Morse aller-retour exact) ; cette vérification n'est pas dans la
suite `unittest` car elle demande un navigateur.

## Limites honnêtes

- C'est un **rapport engendré**, pas un moteur : HERMÈS ne tourne pas dans le
  navigateur ; ses mathématiques restent en Python (`omega_hermes/`). La page le dit.
- Les deux éléments interactifs sont vérifiés à la main et en Chromium sans tête,
  mais ne font pas partie de la suite `unittest` automatique.
- La page reflète l'état des évidences **au moment de la génération** ; relancer les
  bancs puis `python3 -m console.generer` pour la rafraîchir.
- Le « télégraphe qui refuse » (§8.2) n'est pas présenté : il n'est pas implémenté.
