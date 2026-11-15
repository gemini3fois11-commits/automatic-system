# Lancer OMEGA-HERMÈS dans Google Cloud Shell

Cloud Shell offre un **aperçu web** intégré : on sert les pages sur un port, on
clique « Aperçu sur le Web », et on navigue. Comme c'est *votre* machine Cloud
Shell, l'aperçu fonctionne vraiment (contrairement au `127.0.0.1` d'un conteneur
distant, qui est une autre machine).

## 1. Cloner le dépôt

Le dépôt est **privé** : il faut s'authentifier. Le plus simple dans Cloud Shell,
où `gh` est préinstallé :

```bash
gh auth login                                   # HTTPS, suivre les invites
git clone -b claude/inversion-system-algebra-0ju4et \
  https://github.com/gemini3fois11-commits/automatic-system.git
cd automatic-system
```

## 2. Naviguer les tableaux de bord (statique, aucune installation)

```bash
python3 -m http.server 8080
```

Puis : bouton **« Aperçu sur le Web »** (en haut à droite de Cloud Shell) →
**« Prévisualiser sur le port 8080 »**. La page d'accueil (`index.html`) mène aux
trois vues : console, architecture, cycle orchestrateur.

> Autre port (p. ex. 8050) : `python3 -m http.server 8050`, puis dans l'aperçu
> « Changer de port » → 8050.

Pour régénérer le tableau de bord depuis les évidences courantes :

```bash
pip install -e .            # dépendances (numpy)
python3 -m console.generer  # réécrit console/plateforme-omega-hermes-v1-0.html
```

## 3. Les portes *vivantes* (interactives)

Chaque porte est un serveur distinct, sur sa boucle locale. Après
`pip install -e .` :

```bash
omega-gardien       # mandataire à allowlist   → écoute :8090
omega-passerelle    # passerelle Ed25519        → écoute :8077
omega-terminal      # terminal authentifié      → écoute :8076
```

Pour en prévisualiser une : lancez-la, puis « Aperçu Web → Changer de port » vers
son port. Elles démarrent en **SETUP_MODE** : vous choisissez un mot de passe sur
la page avant toute action. Jamais choisi par l'agent, jamais écrit dans un journal.

## 4. Vérifier la preuve soi-même

```bash
omega-preuve verifier CHEMIN/journal.jsonl \
  --temoin CHEMIN/journal.temoin.jsonl --secret ~/coffre/t.secret
# sortie 0 = intègre · 3 = chaîne rompue · 4 = témoin en désaccord
```

Voir [`OPERATION.md`](OPERATION.md) pour le détail de chaque porte.
