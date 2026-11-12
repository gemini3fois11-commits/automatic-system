# console — présentation — `[VÉRIFIÉ]`

## Rôle

Console unifiée (blueprint §8.1) : un **HTML statique auto-contenu** généré depuis les
fichiers `*_evidence.json`. Aucun CDN, aucun compte, aucun serveur obligatoire. Tout
chiffre affiché vient d'un fichier d'évidence produit par exécution. La mission est
affichée comme **proposée, en attente de confirmation du propriétaire** (§1.1).

## Usage

```bash
python3 -m console.generer      # console/plateforme-omega-hermes-v1-0.html
```

Vérification en navigateur (Chromium via Playwright, pré-installé en environnement
cloud) : 0 erreur console, 0 débordement horizontal à 375 px et 1280 px, tous les
liens d'évidence existent.

```bash
node console/verifier.js
python3 -m unittest console.test_console
```

## Limites honnêtes

- HTML statique : la page présente l'état du commit qui l'a générée ; elle ne se
  rafraîchit pas. Pour voir un nouvel état, relancer `python3 -m console.generer`.
- Le télégraphe est présenté comme **composant**, pas en page d'accueil (§8.2).
- Pas de JavaScript propre à la page : les évidences sont lues côté Python au moment
  de la génération et inscrites dans le HTML. La page reste utilisable sans JS.
- Ne pas déployer la page sur un serveur accessible depuis Internet : elle contient
  des références de chemins locaux et des contenus de limites assumés comme internes.
