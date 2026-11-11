# Sécurité

Ce dépôt est une **démonstration défensive**, pas un outil de production ni une
certification (blueprint §1.5, §10.2). Ce fichier décrit l'état réel du dépôt,
pas l'état visé par le blueprint.

## Ce qui existe et ce que ça garantit

| Composant | Garantie | Étiquette |
|---|---|---|
| `socle_preuve/` — chaîne Γ | Toute modification d'un bloc sans recalcul est détectée et le `seq` fautif est nommé | voir `socle_preuve/preuve_evidence.json` |
| `socle_preuve/` — témoin HMAC / Ed25519 | Une réécriture *avec* recalcul de la chaîne est détectée bloc par bloc, tant que l'attaquant n'a pas le secret du témoin | idem |
| `socle_preuve/ed25519.py` | Conforme aux vecteurs RFC 8032 testés | idem |
| `rinv/` | Implémentation de référence de l'algèbre R⁻¹ (antérieure au blueprint) | tests `tests/` |

## Ce que le dépôt ne protège pas

- Un attaquant qui contrôle la machine : tant que le secret du témoin vit sur la
  même machine que le journal, il peut réécrire et resceller (§3.2).
- La troncature conjointe du journal **et** du fichier du témoin : sans ancre de
  tête externe, un retour en arrière cohérent des deux n'est pas détectable.
- Une signature atteste les octets signés, pas la légitimité de leur contenu (P-SIG-29).
- Aucun service réseau n'est livré à ce stade : GARDIEN, passerelle et terminal sont `[SPÉCIFIÉ]`.

## Lignes rouges

Le blueprint §10.3 s'applique sans exception : pas d'exécution distante non
authentifiée, pas de persistance cachée, pas de capture de frappes au niveau
caractères, pas d'outillage offensif.

## Secrets

Aucun secret dans le dépôt ni dans un journal. Les secrets de témoin sont créés
par `python3 -m socle_preuve keygen-*` dans un fichier mode 600 choisi par
l'opérateur, et `.gitignore` exclut `*.secret` et `*.cle`.

## Signaler un problème

Ouvrir une issue sur le dépôt, sans y joindre de secret.
