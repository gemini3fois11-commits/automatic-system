# rinv — `[VÉRIFIÉ]`

## Rôle

Implémentation de référence de l'algèbre d'inversion système R⁻¹ = H / L
(`docs/algebre-inversion-systeme.md`), assemblée en un seul système défensif :
une trame reçue sur un canal volatil n'entre dans le registre canonique Γ que si
elle passe son CRC puis les invariants I₁–I₅, et **chaque décision, refus
compris, est inscrite dans une chaîne Γ scellée par un témoin** (`socle_preuve`).

## Usage

```python
from socle_preuve.gamma import Chaine
from socle_preuve.temoin import ScelleurHMAC, Temoin
from rinv import InvariantGate, Ledger, VoidMonitor

registre = Ledger("Γ", "registre.jsonl", temoin=Temoin("registre.temoin.jsonl", scelleur))
journal = Chaine("decisions.jsonl", temoin=Temoin("decisions.temoin.jsonl", scelleur))
porte = InvariantGate(registre, {"alpha"}, key=cle_agents, journal=journal)
moniteur = VoidMonitor(journal=journal)
verdict = porte.admit(evenement)        # verdict.code : identifiant stable
```

Codes de la porte : `invariants_ok`, `rejeu_idempotent`, `registre_etranger`,
`agent_non_autorise`, `agent_en_quarantaine`, `signature_invalide`,
`event_id_reutilise`, `etat_perime`, `entropie_nulle`, `horloge_figee`.
Codes de trame : `trame_tronquee`, `fanion_absent`, `longueur_incoherente`,
`crc_invalide`, `payload_trop_long`. Journal : `quarantaine_douce`,
`silence_depasse`, `processus_mort`, `battement_muet`.

## Tests

```bash
python3 -m unittest tests.test_rinv tests.test_systeme
python3 -m rinv.systeme
```

Évidence produite : `rinv/systeme_evidence.json` (graine 7).

## Limites honnêtes

- Données synthétiques ; les canaux sont des fichiers locaux, aucune liaison
  radio ou AFSK réelle. La trame n'est pas une trame HDLC complète.
- Dans la démonstration, les 15 s du Void Monitor sont simulées par une horloge
  injectée ; l'Auto-Suture tue et relance de vrais processus.
- Le témoin est local (§3.2) : qui contrôle la machine contrôle le secret.
- La quarantaine d'agent est en mémoire, journalisée mais perdue au redémarrage.
- I₂ sans clé ne prouve que l'intégrité ; avec clé, elle repose sur un secret
  partagé par tous les agents autorisés.
- `Ledger` relit toute la chaîne à chaque opération : correct mais linéaire.
- Les formules des sections I à III et V de la théorie restent des cadrages ;
  seules les parties listées « Implémenté et testé » en V.5 sont vérifiées.
