# telegraphe — transport scellé — `[VÉRIFIÉ]`

> Les quatre sections sont imposées (blueprint §0, §11.4). Aucun chiffre écrit à
> la main : tout vient de [`telegraphe_evidence.json`](telegraphe_evidence.json),
> produit par `python3 -m telegraphe.banc`.

## Rôle

Émettre un message par les anciens transports — Morse (1844) et AFSK Bell 202
(1976) — et **sceller chaque émission** dans une chaîne Γ témoignée. La nouveauté
revendiquée n'est ni le Morse ni la radio : c'est le sceau vérifiable par un
témoin sur le transport (blueprint §8.2). Le CRC **détecte** les erreurs ; il
n'authentifie pas. Ce qui authentifie, c'est le témoin : réécrire une émission
déjà scellée est refusé bloc par bloc, même après recalcul de toute la chaîne.

## Usage

```bash
python3 -m telegraphe.banc                 # bout en bout, écrit telegraphe_evidence.json
python3 -m unittest telegraphe.test_trame telegraphe.test_afsk \
                    telegraphe.test_morse telegraphe.test_registre
```

- `trame` : trame HDLC, bourrage de bits, FCS **CRC-16/X-25** (contrôle `b"123456789"` = `0x906E`).
  Refus (identifiants stables) : `aucun_fanion`, `bourrage_invalide`, `trame_trop_courte`,
  `longueur_non_octet`, `crc_invalide`.
- `afsk` : modem Bell 202 — mark 1200 Hz / space 2200 Hz, 1200 bauds, NRZI, phase
  continue, démodulation Goertzel, export/lecture WAV PCM 16 bits.
- `morse` : code international ; décodeur à **unité de temps adaptative** (l'unité
  est estimée depuis le signal, pas donnée). Refus : `caractere_hors_code`,
  `symbole_inconnu`, `aucun_son`, `vide`.
- `registre` : scelle chaque émission (texte, octets, CRC, taille du signal — jamais
  le son) dans une chaîne Γ du socle de preuve avec témoin HMAC ou Ed25519.

## Tests

```bash
python3 -m unittest telegraphe.test_trame telegraphe.test_afsk telegraphe.test_morse telegraphe.test_registre
```

Évidence produite : `telegraphe/telegraphe_evidence.json` (graine 7). Elle porte
l'aller-retour AFSK exact (mémoire et WAV), le test de corruption (aucun octet faux
livré), le Morse adaptatif sous gigue, l'accord du témoin et la détection de
réécriture. Les repères exacts (octets, bits, échantillons, durée, CRC) sont dans
le fichier, pas ici.

## Limites honnêtes

- Les repères mesurés le sont **à 48 000 Hz** : ce ne sont pas ceux du blueprint
  (22 050 Hz, 6 909 échantillons, CRC `0x141e`), calculés sur un autre message et
  une autre fréquence. On ne recopie pas un chiffre non reproduit.
- La démodulation aligne ses fenêtres sur le **débit connu** du flux généré ici :
  pas de récupération d'horloge en aveugle.
- **Voie microphone** : `[EXPÉRIMENTAL]`, non implémentée, jamais promise (§8.2).
- Le CRC n'authentifie pas. Les garanties du sceau tombent si le secret du témoin
  vit sur la même machine que le journal (§3.2), ou sous troncature cohérente des
  deux fichiers.
- Le décodeur Morse adaptatif suppose au moins un élément d'une unité (un point ou
  un silence intra-caractère) ; un message tout en traits surestime l'unité.
- Le **« télégraphe qui refuse »** (BOB en réception, quarantaine de l'inconnu,
  §8.2) n'est **pas** implémenté : il attend la décision du propriétaire.
