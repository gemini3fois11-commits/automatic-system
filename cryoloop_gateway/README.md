# cryoloop_gateway — passerelle CryoLoop — `[VÉRIFIÉ]`

## Rôle

Le patron des portes du projet (blueprint §3.4) : elle **reçoit, vérifie, inscrit et
répond un verdict. Elle n'exécute rien**, et un test statique vérifie qu'elle n'importe
aucun moyen de le faire. Tickets Ed25519 vérifiés contre une clé publique épinglée,
anti-rejeu persistant (relu depuis Γ au redémarrage), session authentifiée, journal Γ
de chaque décision et de chaque événement d'authentification.

## Usage

Initialisation, **par le propriétaire uniquement** :

```bash
python3 -m cryoloop_gateway.keygen --cle-privee ~/coffre/passerelle.cle   # hors du dépôt
python3 -m cryoloop_gateway.gateway                                       # 127.0.0.1:8077
# puis choisir le mot de passe : POST /api/setup {"mot_de_passe": "…"} (12 caractères min.)
```

Émettre un ticket (côté propriétaire) puis le présenter :

```bash
python3 -m cryoloop_gateway.ticket --cle-privee ~/coffre/passerelle.cle --action inscrire > t.json
```

API : `GET /api/etat` (public) · `POST /api/setup` · `POST /api/login` · `POST /api/logout` ·
`POST /api/ticket` · `GET /api/journal` (authentifiés). Refus : `non_initialisee` (503),
`non_authentifie` (401), `ticket_malforme` (400), `signature_invalide`, `ticket_rejoue`,
`ticket_expire`, `ticket_pas_encore_valide`, `fenetre_invalide` (403), `hote_refuse` (421),
`origine_refusee` (403).

## Tests

```bash
python3 -m unittest cryoloop_gateway.test_gateway      # 25 tests
```

## Limites honnêtes

- **Non initialisée dans ce dépôt** : ni clé, ni mot de passe. Le dossier `etat/` est
  ignoré par git. Je n'ai choisi ni l'une ni l'autre, et je ne le ferai pas.
- Un seul mot de passe partagé ; pas de TLS : boucle locale uniquement, ne jamais exposer.
- Une signature atteste les octets du ticket, pas la légitimité de son contenu (P-SIG-29).
- L'anti-rejeu repose sur le journal local : qui contrôle la machine contrôle la mémoire
  des tickets vus.
- Ed25519 pur Python, pas à temps constant : la passerelle **vérifie**, elle ne signe pas.
