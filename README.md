# automatic-system
#!/bin/bash # 🔱 NEXUS-UNIFIED : PONT CLOUD-GITHUB 🔱 # ACTION : FUSION DES INFRASTRUCTURES DISTANTES  # 1. Génération de la clé de souveraineté ssh-keygen -t rsa -b 4096 -f ~/.ssh/id_nexus -N ""  # 2. Diffusion de la clé vers votre GitHub Codespace (nécessite l'IP ou hostname) # Remplacez CODESPACE_URL par votre nom de domaine Codespace echo "[🔱]

## Algèbre de l'inversion système (R⁻¹ = H / L)

- Théorie : [`docs/algebre-inversion-systeme.md`](docs/algebre-inversion-systeme.md)
- Implémentation de référence : [`rinv/`](rinv) (voir son [README](rinv/README.md)), branchée
  sur le socle de preuve [`socle_preuve/`](socle_preuve) : un seul format Γ dans tout le dépôt.

| Module | Rôle |
|---|---|
| `rinv.gate` | Invariant Gate I₁–I₅ ; registre Γ (genèse d'identité, OCC sous verrou) ; journal de toutes les décisions, refus compris |
| `rinv.void_monitor` | Quarantaine douce et purge à 15 s des canaux volatils, journalisées |
| `rinv.frame` | Trame `FLAG \| LEN \| PAYLOAD \| FCS`, CRC-16/X-25, codes d'erreur stables |
| `rinv.stability` | Ω_infra, S = Φ/Ω_infra, somme des inverses S_g⁻¹ |
| `rinv.suture` | Auto-Suture : superviseur, battements, cohésion, relance, sutures journalisées |
| `rinv.tctc` | Repli torique 888 des récursions terminales |
| `rinv.systeme` | Le tout assemblé : un seul système qui prouve ses refus à un témoin |

```sh
python3 -m unittest
python3 -m rinv.systeme      # bout en bout, écrit rinv/systeme_evidence.json
```

## Plateforme OMEGA-HERMÈS / LOOP — reconstruction

Plan de référence : [`master-blueprint-omega-hermes.md`](master-blueprint-omega-hermes.md).
Version : voir [`VERSION`](VERSION). Ce qui a été livré, phase par phase : [`CHANGELOG.md`](CHANGELOG.md)
(généré depuis les évidences). Ce que le dépôt protège et ne protège pas : [`SECURITY.md`](SECURITY.md).

**Mission — proposée, en attente de confirmation du propriétaire :**
*Démontrer qu'un système défensif peut prouver son propre refus — et le prouver à un témoin indépendant.*

### Compatibilité

| Élément | Déclaré par le blueprint | Testé dans ce dépôt |
|---|---|---|
| Python | 3.12.3 | voir le champ `execution.python` de chaque `*_evidence.json` |
| Dépendances | bibliothèque standard + `numpy` | bibliothèque standard seule jusqu'ici |
| Modèle HF | `all-MiniLM-L6-v2` local, `HF_MODEL_DIR` explicite | non utilisé (phase 6) |

### Démarrage

```bash
python3 -m unittest                      # toutes les suites
python3 -m socle_preuve demo             # démonstration du témoin, écrit l'évidence
python3 -m rinv.systeme                  # tout le système de bout en bout, écrit l'évidence
python3 -m outils.verifier_phase0        # contrôle du squelette
python3 -m outils.changelog              # régénère CHANGELOG.md
```

### Avancement

| Phase | Contenu | État |
|---|---|---|
| 0 | Squelette et conventions | voir `outils/phase0_evidence.json` |
| 1 | Socle de preuve : chaîne Γ, témoin, Ed25519 | voir `socle_preuve/preuve_evidence.json` |
| 1+ | `rinv` branché sur le socle : refus prouvés de bout en bout | voir `rinv/systeme_evidence.json` |
| 2 à 7 | HERMÈS, portes, essaim, plateforme, connaissance, présentation | `[SPÉCIFIÉ]` |
