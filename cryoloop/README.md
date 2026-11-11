# cryoloop — `[SIMULÉ]`

## Rôle

Validateur exécutable du cycle CRYOLOOP Ω∞ (`cryoloop/SPEC.md`). Il fait passer une
archive de preuves par les huit étapes du cycle et rend une décision : ACCEPT
(candidat Γ), PENDING (Γ préservé), QUARANTINE (preuves isolées) ou REJECT. Il est en
lecture seule : **il ne committe jamais Γ** (CL-I5, « Observation ≠ Autorisation »).

## Usage

```bash
python3 -m cryoloop valider ARCHIVE --cle-publique <hex> --gamma registre.jsonl \
        --journal cycles.jsonl --sortie candidats/
python3 -m cryoloop banc            # matrice de scénarios + LOOP 001, écrit l'évidence
```

Codes de sortie : `0` ACCEPT · `5` PENDING · `6` QUARANTINE · `7` REJECT · `2` usage.
Le périmètre (`--perimetre DON-DC01 --debut 18 --fin 100 --evenements 21 --dimension-ekf 64`)
est fixé par l'opérateur et comparé au manifeste, jamais l'inverse.

Format d'archive proposé, `cryoloop-archive-v0` :

```text
ARCHIVE/
  MANIFEST.json      {"format", "perimetre", "epoques": [18, 100], "evenements_attendus": 21,
                      "expected_state_hash", "fichiers": {"chemin": "sha256", …}}
  MANIFEST.sig       signature Ed25519 (hex) des octets de MANIFEST.json
  evenements/E01.json   {"id", "epoque", "prev": sha256 de l'événement précédent, "ekf", "mesures"}
  ekf/EKF_Matrix_State_E01.json   {"epoque", "P_post", "P_prior", "H", "R", "K"}
  mesures/E01.json   {"memoire": [nombres], "thermique": [nombres]}
```

Les archives réelles sont attendues dans `cryoloop/archives/DON-DC01/`.

## Tests

```bash
python3 -m unittest cryoloop.test_validateur
python3 -m cryoloop banc
```

Évidence produite : `cryoloop/cryoloop_evidence.json`.

## Limites honnêtes

- **`[SIMULÉ]`** : le banc fabrique des archives synthétiques. Il prouve que le validateur
  décide comme prévu ; il ne dit rien des archives DON-DC01, **qui n'ont pas été fournies**.
  Sur elles, LOOP 001 est PENDING (`entrees_absentes`).
- Le format v0 est une proposition et devra être adapté aux vrais fichiers.
- La provenance n'est établie que par un manifeste signé avec une clé épinglée ; la clé du
  banc est publique par construction.
- Mémoire et thermique : présence et forme contrôlées, valeurs jamais interprétées. Aucun
  seuil n'a été inventé.
- P6 (SQLite WAL) n'est pas couvert ; voir `SPEC.md`, décision 5.
- L'archive est lue entièrement en mémoire (plafond 512 Mio).
