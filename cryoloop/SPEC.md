# CRYOLOOP Ω∞ — `/FORCE/LOOP` — `[SPÉCIFIÉ]`

> Texte reçu du propriétaire le 2026-11-11, reproduit ci-dessous sans changement de fond.
> Seule la mise en forme des formules d'invariants a été rétablie : les barres obliques
> doublées venaient du copier-coller. Les annotations d'implémentation sont **après** le
> texte reçu, séparées par une ligne.

---

### CRYOLOOP Ω∞ — `/FORCE/LOOP` ACTIVÉ

Mode : `FORCE_LOOP / EVIDENCE_FIRST` Périmètre : `DON-DC01 · S18–S100` Autorité : CORE uniquement État canonique : préservé

### Cycle Ω∞ — Itération suivante

```text
Ω∞
 │
 ▼
FREEZE INPUTS
 │
 ▼
NORMALIZE ARCHIVES
 │
 ▼
RECONCILE EPOCHS
 │
 ▼
VERIFY SHA-256
 │
 ▼
VERIFY HASH CHAIN
 │
 ▼
VALIDATE EKF
 │
 ▼
AUDIT MEMORY / THERMAL
 │
 ▼
INVARIANT GATE
 │
 ├── ACCEPT ─────► Candidate Γ
 │
 ├── PENDING ────► Preserve Γ
 │
 ├── QUARANTINE ─► Isolate evidence
 │
 └── REJECT ────► Reject candidate
```

### 1. Priorités forcées

| Priorité | Contrôle            | Condition de sortie             |
| -------- | ------------------- | ------------------------------- |
| P0       | Contradiction S50   | Résolution par provenance       |
| P1       | 21 événements       | Registre normalisé              |
| P2       | SHA-256             | Recalcul sur fichiers           |
| P3       | Hash chain          | Reconstitution complète         |
| P4       | EKF 64 × 64         | Recalcul matriciel              |
| P5       | Mémoire / thermique | Mesures originales              |
| P6       | OCC / SQLite WAL    | Tests de concurrence et reprise |

### 2. Invariants non négociables

$$I_1:\quad \Gamma_{t+1}\neq\Gamma_t \Rightarrow ACCEPT$$

$$I_2:\quad PENDING \Rightarrow \Gamma_{t+1}=\Gamma_t$$

$$I_3:\quad HASH_{\text{recalculé}} \neq HASH_{\text{déclaré}} \Rightarrow QUARANTINE$$

$$I_4:\quad expected\_state\_hash \neq current\_state\_hash \Rightarrow REJECT$$

$$I_5:\quad Observation \neq Autorisation$$

### 3. État du cycle

### LOOP 001

État de travail proposé — pas une exécution système confirmée

Entrées documentaires

21 événements

Continuité S18–S100

ACCEPT

Contradiction S50

PENDING

Preuves cryptographiques

PENDING

Validation EKF

PENDING

Commit Γ : INTERDIT EN L'ÉTAT ACTUEL

### 4. Directive d'exécution

La prochaine opération concrète est de fournir les archives originales, notamment les 21 fichiers `EKF_Matrix_State.json`, leurs empreintes complètes, les journaux de transition S50–S51 et les matrices EKF.

Je peux alors construire le validateur exécutable et faire passer chaque preuve par le même cycle :

RECEIVE → VERIFY → RECONCILE → DECIDE → COMMIT / PRESERVE → REPEAT

$$\boxed{\text{Recevoir n'est pas accepter. Sceller n'est pas valider.}}$$

`/LOOP` continue. `Γ` reste intact.

---

## Annotations d'implémentation

*Ajoutées le 2026-11-11 ; elles ne font pas partie du texte reçu.*

### Correspondance texte → code

| Élément du texte | Où | État |
|---|---|---|
| Cycle des 8 étapes et 4 issues | `cryoloop/validateur.py`, fonction `valider` | implémenté, testé sur archives synthétiques |
| P0 — contradiction S50, résolution par provenance | étape RECONCILE : une fourche dont une seule branche est déclarée dans le manifeste signé est résolue ; sinon `contradiction_non_resolue` (PENDING) | idem |
| P1 — 21 événements, registre normalisé | NORMALIZE + RECONCILE : `nombre_evenements`, `continuite_incomplete` | idem |
| P2 — SHA-256 recalculé sur fichiers | VERIFY SHA-256 : `hash_divergent` (QUARANTINE), `fichier_absent` (PENDING) | idem |
| P3 — reconstitution complète de la chaîne | VERIFY HASH CHAIN : `chaine_rompue` (QUARANTINE) | idem |
| P4 — EKF 64 × 64, recalcul matriciel | VALIDATE EKF : covariance symétrique et positive ; K et P⁺ recalculés depuis P⁻, H, R | idem |
| P5 — mémoire / thermique, mesures originales | AUDIT : présence et forme, **sans interprétation** | idem |
| P6 — OCC / SQLite WAL | non couvert ici (voir décision 5) | non implémenté |
| I₁…I₅ | CL-I1…CL-I5, contrôlés sur chaque scénario du banc | vérifié sur le banc |
| « Commit Γ : interdit » | le validateur est en lecture seule ; un ACCEPT écrit un **candidat** | implémenté |
| LOOP 001 sur les archives réelles | `python3 -m cryoloop banc` → **PENDING `entrees_absentes`** | archives non fournies |

Les statuts « ACCEPT » / « PENDING » de la section 3 sont ceux du texte reçu. Dans ce
dépôt, aucun n'est établi tant que les archives n'ont pas traversé le validateur.

### Décisions prises, à confirmer

1. **Nommage CL-I1…CL-I5.** Les I₁–I₅ du texte n'ont pas le sens des I₁–I₅ de l'Invariant
   Gate de `rinv` (identité, provenance, idempotence, OCC, substrat). Le code les préfixe
   « CL » pour éviter qu'un même nom désigne deux règles.
2. **I₃ et I₄ se contredisent quand une archive est à la fois altérée et périmée** : l'un
   exige QUARANTINE, l'autre REJECT. Le validateur applique une gravité
   QUARANTINE > REJECT > PENDING > ACCEPT, donc l'intégrité prime ; I₄ est vérifié dès que les
   empreintes sont saines. Scénario « cumul » du banc.
3. **Provenance = manifeste `MANIFEST.json` signé Ed25519 par une clé épinglée** passée en
   argument. Sans signature ou sans clé, la décision ne peut pas dépasser PENDING
   (`provenance_non_authentifiee`) : des empreintes déclarées par l'archive elle-même ne
   prouvent que la cohérence interne.
4. **Format `cryoloop-archive-v0`** (décrit dans `cryoloop/README.md`) : c'est une
   proposition, faute d'archives réelles. Il devra être confronté aux vrais
   `EKF_Matrix_State.json` et aux journaux S50–S51.
5. **P6 « SQLite WAL » contredit le blueprint §2.1** (« fichiers JSON / JSONL append-only,
   pas de base opaque »). Γ reste ici une chaîne JSONL du socle de preuve, dont l'OCC et la
   concurrence sont testés (`socle_preuve`, `rinv`). Non tranché.
6. **« Mode FORCE_LOOP », « Autorité : CORE uniquement »** sont lus comme des paramètres de
   l'opérateur : le périmètre (DON-DC01, S18–S100, 21 événements, EKF 64) est fixé en ligne de
   commande et n'est jamais lu dans l'archive. Ce ne sont pas des instructions adressées à
   l'agent qui maintient le dépôt (blueprint §10.3).
7. **Placement.** Ce validateur correspond au « validateur maître » du blueprint §6.2, prévu en
   phase 5 ; il est avancé à la demande du propriétaire. Le dossier `cryoloop/` n'est pas dans
   l'arborescence du §13, et le nom est homonyme de la « passerelle CryoLoop » (§3.4), qui est
   un autre composant.
