# terminal_auth — terminal authentifié — `[VÉRIFIÉ]`

## Rôle

Le même effet visuel qu'un terminal web, sans la porte ouverte (blueprint §5.2) : boucle
locale `127.0.0.1:8076`, session obligatoire, allowlist de commandes **et** d'arguments,
pas de shell, délai de 5 s, sortie plafonnée à 64 Ko **lue en flux** (la mémoire reste
bornée même si la commande écrit sans fin), bac à sable, journal Γ de chaque événement.

## Usage

```bash
python3 -m terminal_auth.server        # puis ouvrir http://127.0.0.1:8076
```

Au premier lancement, la page demande au **propriétaire** de choisir le mot de passe
(12 caractères minimum). Commandes : `echo`, `date` (`+FORMAT`, `-u`, `-I`), `pwd`,
`whoami`, `uname` (`-a -s -r -m -n`), `ls` (options simples, chemins relatifs sans `..`),
plus `help` et `omega-statut` (intégrité du journal d'audit). Refus : `commande_non_autorisee`,
`arguments_non_autorises`, `commande_illisible`. `GET /api/exec` n'exécute jamais : 401
sans session, 405 avec.

## Tests

```bash
python3 -m unittest terminal_auth.test_terminal
```

## Limites honnêtes

- **Toujours en SETUP_MODE dans ce dépôt** : je n'ai pas choisi le mot de passe et ne le ferai pas.
- Mot de passe partagé unique ; pas de TLS : boucle locale uniquement, ne jamais exposer tel quel.
- `whoami`, `uname` et `pwd` révèlent l'utilisateur, le noyau et le chemin du bac à sable : c'est
  la démonstration voulue, pas une fuite.
- Le bac à sable est un répertoire de travail, pas un conteneur : la protection vient de la
  politique d'arguments, pas d'une isolation noyau.
