# socle_preuve — `[VÉRIFIÉ]`

## Rôle

Bibliothèque partagée unique de preuve (blueprint §3) : chaîne Γ append-only
chaînée par SHA-256, témoin indépendant (HMAC-SHA256 ou Ed25519 à clé publique
épinglée) et Ed25519 pur Python (RFC 8032). Tout module qui journalise une
décision doit passer par `socle_preuve.gamma.Chaine`, pas par un format à lui.

## Usage

```python
from socle_preuve.gamma import Chaine
from socle_preuve.temoin import ScelleurHMAC, Temoin

chaine = Chaine("audit.jsonl", temoin=Temoin("audit.temoin.jsonl", ScelleurHMAC(secret)))
chaine.inscrire("requete", "REFUS", "hote_non_autorise", {"hote": "example.org"})
```

```bash
python3 -m socle_preuve keygen-hmac temoin.secret            # 32 octets, mode 600, refuse d'écraser
python3 -m socle_preuve keygen-ed25519 temoin.cle            # affiche la clé publique à épingler
python3 -m socle_preuve verifier audit.jsonl                 # chaîne seule
python3 -m socle_preuve verifier audit.jsonl --temoin audit.temoin.jsonl --secret temoin.secret
python3 -m socle_preuve verifier audit.jsonl --temoin audit.temoin.jsonl --cle-publique <hex>
python3 -m socle_preuve demo                                 # démonstration rejouable + évidence
```

Codes de sortie : `0` intègre et témoin en accord · `2` usage, fichier absent ou
secret pas en mode 600 · `3` chaîne rompue (seq nommé) · `4` témoin en désaccord.

Raisons (identifiants stables) — chaîne : `json_invalide`, `champ_manquant`,
`seq_inattendu`, `prev_hash_rompu`, `hash_invalide` ; témoin : `chaine_rompue`,
`desaccord_temoin`, `sceau_invalide`, `temoin_orphelin`, `bloc_non_temoigne`,
`temoin_incoherent`, `temoin_illisible`.

## Tests

```bash
python3 -m unittest socle_preuve.test_ed25519 socle_preuve.test_gamma socle_preuve.test_temoin
python3 -m socle_preuve demo
```

Évidence produite : `socle_preuve/preuve_evidence.json` (scénarios joués par le
vrai CLI, contrôles RFC 8032, durées Ed25519 médianes avec plancher soustrait).

## Limites honnêtes

- **Témoin local** : tant que le secret vit sur la même machine que le journal, un
  attaquant qui contrôle la machine peut réécrire et resceller. Le témoin ne
  devient indépendant qu'avec un secret hors machine (§3.2, §14.3 point 4).
- **Troncature cohérente** : supprimer la fin du journal *et* la fin du fichier
  témoin n'est pas détectable sans ancre de tête externe. Tronquer le journal
  seul l'est (`temoin_orphelin`).
- **Ed25519 pur Python, pas à temps constant** : bon pour vérifier et démontrer,
  pas pour signer avec une clé de valeur sur une machine partagée.
- **RFC 8032** : 4 des 5 vecteurs Ed25519 de §7.1 (TEST 1024 non transcrit). Le
  blueprint parle de « 8/8 » sans dire lesquels ; le compte réel est dans l'évidence.
- **Lecture complète à chaque écriture** : `inscrire` relit et revérifie toute la
  chaîne sous verrou. Correct, mais linéaire en taille du journal.
- Une signature atteste les octets signés, pas la légitimité du contenu (P-SIG-29).
