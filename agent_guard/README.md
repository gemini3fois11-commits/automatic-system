# agent_guard — GARDIEN — `[VÉRIFIÉ]`

## Rôle

Mandataire HTTP pour agents IA : une requête n'est transmise que si son hôte figure
**exactement** dans `allowlist.json` (`example.com`, `neverssl.com`, `info.cern.ch`).
Chaque décision, autorisation comme refus, est inscrite dans une chaîne Γ du socle de
preuve (`guard_audit.jsonl`, mode 600), scellable par un témoin HMAC. Réponse à la
nécessité n° 1 de l'incident de juillet 2026 : empêcher des agents de sortir par un
canal non prévu.

## Usage

```bash
python3 -m agent_guard.guard [--temoin-secret temoin.secret]   # 127.0.0.1:8090
python3 -m agent_guard.guard --verify                          # exit 0 intègre, 3 rompue
curl --proxy http://127.0.0.1:8090 http://example.com/
curl http://127.0.0.1:8090/api/status
```

Refus (identifiants stables) : `hote_non_autorise` (403), `port_non_autorise` (403),
`tls_non_inspecte` (CONNECT, 403), `schema_non_http` (403), `corps_trop_gros` (> 1 Mio, 413),
`encodage_non_supporte` (chunked, 411), `amont_injoignable` (502), `reponse_trop_grosse` (502).
Signaux, qui marquent sans bloquer : `haute_entropie`, `base64_suspect`,
`exfiltration_chemin`, `exfiltration_hote`, `url_anormale`.

Proxy amont : `GARDIEN_AMONT=http://utilisateur:motdepasse@hote:port`, relu à chaque
requête ; les identifiants partent vers l'amont et ne sont jamais journalisés. Le
journal garde l'empreinte du chemin et du corps, jamais leur contenu.

## Tests

```bash
python3 -m unittest agent_guard.test_guard agent_guard.test_charge
python3 -m agent_guard.banc            # écrit agent_guard/guard_evidence.json
```

## Limites honnêtes

- **Le trafic vers les trois hôtes publics n'a pas été joué dans cet environnement** :
  son proxy sortant ne relaie que le HTTPS. Le banc envoie de vraies requêtes HTTP à
  travers un vrai GARDIEN, vers une origine locale qui se fait passer pour ces hôtes.
- Mono-machine, pas de consensus. Pas d'inspection des réponses : une destination
  autorisée compromise reste un risque.
- Le GARDIEN ne couvre que le trafic qui passe par lui ; rien n'y force un agent.
- Pas de tunnel TLS : tout HTTPS est refusé, par conception.
- Heuristiques : signal, jamais preuve. Elles produiront des faux positifs.
- Un refus envoyé sans lire le corps (corps trop gros, chunked) est suivi d'une fermeture différée
  bornée à 4 Mio et 2 s : au-delà, le client voit une connexion coupée au lieu du 413.
