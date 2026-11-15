# Déploiement — un service déclaré, journalisé, installé par vous

`omega-gardien.service` est un **gabarit** d'unité systemd de portée **utilisateur**
(`systemctl --user`). Il fait tourner une porte de la plateforme (ici le GARDIEN)
comme un service ordinaire sous votre compte. C'est volontairement l'opposé d'une
prise de contrôle de la machine :

| Ce gabarit | Ce que la plateforme refuse (§10.3) |
|------------|-------------------------------------|
| installé par vous, à la main | installation automatique par l'agent |
| portée utilisateur, jamais root | service root non déclaré |
| fichier versionné, relisible | persistance cachée (`~/.bashrc`, crontab) |
| journald + chaîne Γ append-only | effacement des journaux |
| écoute `127.0.0.1` seulement | écoute `0.0.0.0` / port caché |

L'agent **n'exécute aucun `systemctl`** et n'installe rien : les commandes
ci-dessous sont à lancer par vous, en connaissance de cause.

## Installer

```
mkdir -p ~/.config/systemd/user
cp deploy/omega-gardien.service ~/.config/systemd/user/
# Adapter dans le fichier : WorkingDirectory, le chemin de omega-gardien, le dossier d'état.
systemctl --user daemon-reload
systemctl --user enable --now omega-gardien
```

Prérequis : `pip install -e .` depuis la racine du dépôt (crée le point d'entrée
`omega-gardien`). Pour qu'un service utilisateur survive à la fermeture de session :
`loginctl enable-linger $USER`.

## Observer

```
systemctl --user status omega-gardien
journalctl --user -u omega-gardien -f
# La preuve propre à la plateforme reste la chaîne Γ, vérifiée par le témoin :
omega-preuve verifier ~/.local/state/omega-hermes/gardien/guard_audit.jsonl
```

## Retirer — sans résidu

```
systemctl --user disable --now omega-gardien
rm ~/.config/systemd/user/omega-gardien.service
systemctl --user daemon-reload
```

## Adapter à une autre porte

Dupliquer le fichier et remplacer `ExecStart` par `omega-passerelle` (8077) ou
`omega-terminal` (8076). Pour des relances bornées **inscrites dans Γ**, faire
lancer par systemd le superviseur de la plateforme plutôt que la porte
directement :

```
ExecStart=%h/.local/bin/omega-superviseur --etat %h/.local/state/omega-hermes/gardien -- %h/.local/bin/omega-gardien
```

systemd garde alors le superviseur en vie ; le superviseur garde la porte en vie
avec des relances bornées et journalisées (1, 2, 4, 8, 8 s, puis abandon).

> Gabarit non testé ici (ce conteneur n'a pas de session systemd utilisateur) :
> vérifiez-le sur votre machine avec `systemd-analyze --user verify
> omega-gardien.service` avant de l'activer.
