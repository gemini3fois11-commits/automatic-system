"""Authentification partagée des portes locales (blueprint §3.4, §5.2).

- Mot de passe choisi par le propriétaire à l'installation (12 caractères minimum),
  jamais par l'agent. Tant qu'il n'est pas choisi, la porte est en SETUP_MODE.
- Stocké dérivé par scrypt salé (fichier mode 600), comparé à temps constant.
  Écart assumé au blueprint, qui dit « SHA-256 salé » : scrypt est lent par
  construction, un SHA-256 se force à des milliards d'essais par seconde.
- 5 échecs en 10 minutes verrouillent la porte 15 minutes.
- Jetons de session de 256 bits, expiration glissante de 30 minutes ; seule leur
  empreinte SHA-256 est gardée en mémoire.
"""

import hashlib
import hmac
import json
import os
import secrets
import threading
import time
from typing import Callable

MIN_LONGUEUR = 12
ECHECS_MAX, FENETRE_S, VERROU_S = 5, 600, 900
SESSION_S = 1800
SCRYPT = {"n": 2 ** 14, "r": 8, "p": 1, "dklen": 32}


class ErreurAuth(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _deriver(mot_de_passe: str, sel: bytes, params: dict) -> bytes:
    return hashlib.scrypt(mot_de_passe.encode("utf-8"), salt=sel, maxmem=64 * 1024 * 1024,
                          **params)


class Authentificateur:
    def __init__(self, fichier, *, horloge: Callable[[], float] = time.monotonic,
                 delai_echec: float = 0.5,
                 evenement: Callable[[str, dict], None] | None = None):
        self.fichier = os.fspath(fichier)
        self._horloge = horloge
        self._delai = delai_echec
        self._evenement = evenement or (lambda type, details: None)
        self._verrou = threading.RLock()
        self._echecs: list[float] = []
        self._verrouille_jusqu_a = 0.0
        self._sessions: dict[str, float] = {}

    @property
    def setup_mode(self) -> bool:
        return not os.path.exists(self.fichier)

    def configurer(self, mot_de_passe: str) -> None:
        if not isinstance(mot_de_passe, str) or len(mot_de_passe) < MIN_LONGUEUR:
            raise ErreurAuth("mot_de_passe_trop_court")
        sel = secrets.token_bytes(16)
        doc = {"alg": "scrypt", **SCRYPT, "sel": sel.hex(),
               "empreinte": _deriver(mot_de_passe, sel, SCRYPT).hex()}
        with self._verrou:
            try:
                fd = os.open(self.fichier, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            except FileExistsError:
                raise ErreurAuth("deja_configure")
            with os.fdopen(fd, "w") as fh:
                json.dump(doc, fh)
        self._evenement("setup_done", {})

    def _verifier(self, mot_de_passe: str) -> bool:
        with open(self.fichier) as fh:
            doc = json.load(fh)
        params = {k: doc[k] for k in SCRYPT}
        calcule = _deriver(mot_de_passe, bytes.fromhex(doc["sel"]), params)
        return hmac.compare_digest(calcule, bytes.fromhex(doc["empreinte"]))

    def connecter(self, mot_de_passe: str) -> str:
        with self._verrou:
            if self.setup_mode:
                raise ErreurAuth("setup_mode")
            maintenant = self._horloge()
            if maintenant < self._verrouille_jusqu_a:
                raise ErreurAuth("verrouille")
            if isinstance(mot_de_passe, str) and self._verifier(mot_de_passe):
                self._echecs.clear()
                jeton = secrets.token_hex(32)
                self._sessions[hashlib.sha256(jeton.encode()).hexdigest()] = maintenant + SESSION_S
                self._evenement("login_ok", {})
                return jeton
            self._echecs = [t for t in self._echecs if maintenant - t < FENETRE_S] + [maintenant]
            self._evenement("login_fail", {"echecs_recents": len(self._echecs)})
            if len(self._echecs) >= ECHECS_MAX:
                self._verrouille_jusqu_a = maintenant + VERROU_S
                self._echecs.clear()
                self._evenement("locked", {"duree_s": VERROU_S})
        if self._delai:
            time.sleep(self._delai)  # frein anti-force brute, hors verrou
        raise ErreurAuth("identifiants_invalides")

    def valider(self, jeton: str | None) -> bool:
        if not jeton:
            return False
        cle = hashlib.sha256(jeton.encode()).hexdigest()
        with self._verrou:
            fin = self._sessions.get(cle)
            maintenant = self._horloge()
            if fin is None or maintenant >= fin:
                self._sessions.pop(cle, None)
                return False
            self._sessions[cle] = maintenant + SESSION_S
            return True

    def deconnecter(self, jeton: str | None) -> None:
        if jeton:
            with self._verrou:
                if self._sessions.pop(hashlib.sha256(jeton.encode()).hexdigest(), None) is not None:
                    self._evenement("logout", {})
