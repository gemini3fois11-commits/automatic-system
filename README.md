# automatic-system
#!/bin/bash # 🔱 NEXUS-UNIFIED : PONT CLOUD-GITHUB 🔱 # ACTION : FUSION DES INFRASTRUCTURES DISTANTES  # 1. Génération de la clé de souveraineté ssh-keygen -t rsa -b 4096 -f ~/.ssh/id_nexus -N ""  # 2. Diffusion de la clé vers votre GitHub Codespace (nécessite l'IP ou hostname) # Remplacez CODESPACE_URL par votre nom de domaine Codespace echo "[🔱]

## Algèbre de l'inversion système (R⁻¹ = H / L)

- Théorie : [`docs/algebre-inversion-systeme.md`](docs/algebre-inversion-systeme.md)
- Implémentation de référence (Python ≥ 3.10, bibliothèque standard seule) : [`rinv/`](rinv)

| Module | Rôle |
|---|---|
| `rinv.gate` | Invariant Gate I₁–I₅ et registre canonique Γ append-only |
| `rinv.void_monitor` | Quarantaine douce et purge à 15 s des tubes volatils |
| `rinv.frame` | Trame `FLAG \| LEN \| PAYLOAD \| CRC-16` |
| `rinv.stability` | Ω_infra, S = Φ/Ω_infra, somme des inverses S_g⁻¹ |
| `rinv.tctc` | Repli torique 888 des récursions terminales |

```sh
python3 -m unittest
```
