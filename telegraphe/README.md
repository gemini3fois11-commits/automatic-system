# telegraphe — composant de transport scellé — `[VÉRIFIÉ]`

## Rôle

Composant Bell 202 (1976) qui **ajoute un sceau vérifiable par un témoin** à un transport
AFSK ancien (blueprint §8.2). La nouveauté revendiquée n'est ni le Morse, ni la radio, ni
le modem : c'est le sceau. Chaque trame reçue est validée par son CRC-16/X-25, décodée,
contrôlée (ordre strict de `seq`) puis inscrite dans une chaîne Γ scellée par un témoin HMAC
ou Ed25519. Un attaquant qui réécrit le texte et recalcule localement passe l'audit
local — le témoin le détecte.

## Usage

```python
from socle_preuve.gamma import Chaine
from socle_preuve.temoin import ScelleurHMAC, Temoin
from telegraphe.transport import Recepteur, emettre

temoin = Temoin("telegraphe.temoin.jsonl", ScelleurHMAC(secret))
journal = Chaine("telegraphe.jsonl", temoin=temoin)
echantillons = emettre(seq=1, texte="CQ CQ DE OMEGA")   # [-1, 1], 22050 Hz
verdict = Recepteur(journal).recevoir(echantillons)
```

Décisions : `trame_scellee` (ACCEPTE) · `crc_invalide` · `enveloppe_malformee` ·
`seq_non_croissant` · `aucune_trame` · `trame_tronquee` · `fanion_absent`.

## Tests

```bash
python3 -m unittest telegraphe.test_afsk telegraphe.test_transport
```

Vecteur de contrôle : CRC-16/X-25 de « 123456789 » = `0x906E`. Trame de 376 bits ↔
6 909 échantillons ≈ 313 ms (chiffres du blueprint reproduits).

## Limites honnêtes

- Démodulation par Goertzel sur 8 décalages de synchronisation : robuste à un léger bruit,
  ce qui rend un test de corruption « 2 bits inversés » insuffisant ; le banc utilise un
  bruit blanc de 8 bits pour forcer la détection.
- **Voie microphone non implémentée** : la modulation produit des flottants et un fichier
  WAV ; aucune capture audio réelle. Le blueprint §8.2 marque cette voie `[EXPÉRIMENTAL]`.
- Ce n'est pas une trame HDLC complète : pas de bourrage de bits côté émission (le CRC et
  l'enveloppe JSON suffisent à l'assurance recherchée), pas de fanion de fin obligatoire.
- `seq` strictement croissant ne protège pas d'une duplication contemporaine (deux
  émetteurs rejouant la même `seq` au même moment) : la couche transport ne gère pas la
  concurrence des émetteurs.
