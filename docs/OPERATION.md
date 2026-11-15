# Guide opérateur — Plateforme OMEGA-HERMÈS

Comment lancer, vérifier et arrêter la plateforme. Chaque porte écoute sur
`127.0.0.1` uniquement ; tout verdict entre dans une chaîne Γ append-only
(mode 600) scellée par un témoin indépendant ; aucun secret ne vit dans le
dépôt. Rien ici ne s'installe seul ni ne tourne en root caché.

## Prérequis

- Python ≥ 3.11, `numpy`.
- `openssl` sur le `PATH` pour deux contrôles d'épinglage TLS (sinon ignorés).
- Lancement depuis la racine du dépôt (`python3 -m <module>`), ou après
  `pip install -e .` (voir `pyproject.toml`).

## 1. Les portes locales

| Porte | Commande | Écoute |
|-------|----------|--------|
| GARDIEN (mandataire HTTP à allowlist) | `python3 -m agent_guard.guard` | `127.0.0.1:8090` |
| Passerelle CryoLoop (vérifie, n'exécute rien) | `python3 -m cryoloop_gateway.gateway` | `127.0.0.1:8077` |
| Terminal authentifié | `python3 -m terminal_auth.server` | `127.0.0.1:8076` |

Options communes : `--port`, `--etat DOSSIER` (chaîne Γ et état), `--temoin-secret FICHIER`
pour la passerelle. `--help` détaille chaque porte.

La passerelle et le terminal démarrent en **SETUP_MODE** : aucune action n'est
acceptée tant que le propriétaire n'a pas fixé un mot de passe via
`POST /api/setup` (jamais choisi par l'agent, jamais collé dans un journal).
Après configuration : verrouillage après 5 échecs, sessions glissantes.

## 2. Clés et tickets de la passerelle

Générer la paire de clés — la clé privée est écrite **hors du dépôt**, mode 600,
jamais écrasée ; seule la clé publique est épinglée :

```
python3 -m cryoloop_gateway.keygen --cle-privee ~/coffre/passerelle.cle
```

Signer un ticket (côté propriétaire) :

```
python3 -m cryoloop_gateway.ticket --cle-privee ~/coffre/passerelle.cle --action inscrire
```

La passerelle vérifie la signature Ed25519 et l'anti-rejeu, **puis n'exécute
rien** : un test statique interdit `subprocess`, `pty`, `ctypes` dans son code.

## 3. Preuve : lire et vérifier la chaîne Γ

Chaque porte écrit un journal `*.jsonl` (un bloc par ligne, chaîné par SHA-256).
Le lire, c'est `cat` ; le **vérifier**, c'est :

```
python3 -m socle_preuve verifier DOSSIER/journal.jsonl \
    --temoin DOSSIER/journal.temoin.jsonl --secret ~/coffre/temoin.secret
```

Sortie 0 = chaîne intègre et témoin en accord ; 3 = chaîne rompue ; 4 = désaccord
du témoin (un bloc a été réécrit, ajouté ou supprimé après coup). Sans `--temoin`,
seule l'intégrité locale est contrôlée — un attaquant qui réécrit *et* recalcule
la chaîne passe le contrôle local mais **jamais** le témoin.

Secrets du témoin (hors dépôt, mode 600) :

```
python3 -m socle_preuve keygen-hmac   ~/coffre/temoin.secret      # témoin HMAC
python3 -m socle_preuve keygen-ed25519 ~/coffre/temoin.cle        # témoin Ed25519
python3 -m socle_preuve demo                                       # démonstration rejouable
```

## 4. Faire tourner un service sous surveillance

Le superviseur relance un service de façon bornée (attentes 1, 2, 4, 8, 8 s ;
5 relances puis abandon), arrête proprement le groupe de processus sur
SIGTERM/SIGINT, et **n'écrit aucune persistance cachée** (ni `~/.bashrc`, ni
crontab, ni service système) — garanti par test.

```
python3 -m runtime.superviseur --etat /run/omega/etat -- python3 -m agent_guard.guard
```

Avant de signaler un PID hérité au redémarrage, son identité est vérifiée par
`/proc/<pid>/cmdline` : un PID recyclé n'est jamais tué.

## 5. Cycle complet et dossier

```
python3 -m plateforme_omega.orchestrator      # lance toutes les suites, écrit l'évidence + le tableau de bord
python3 -m dossier.generer                     # matrice de traçabilité, tests, ruff, couverture → dossier/
```

L'orchestrateur tolère **un** échec documenté sur 21 (la fusion RRF, sous
TF-IDF sur ce corpus) ; tout autre échec est « inattendu » et fait échouer le
cycle. Aucun chiffre n'est saisi à la main : tout vient d'un `*_evidence.json`
produit par exécution.

## 6. Ce que la plateforme ne fait pas

- Pas d'endpoint d'exécution distante : la passerelle vérifie et journalise, elle
  n'exécute pas.
- Pas d'écoute hors `127.0.0.1`, pas de persistance cachée, pas d'effacement de
  journaux.
- Pas de capture d'identifiants au caractère ; seule la dynamique de frappe par
  catégories et timings (`guardian`) est permise.
- Aucune certification revendiquée : seule la discipline d'ingénierie l'est, et
  elle est vérifiable par les commandes ci-dessus.
