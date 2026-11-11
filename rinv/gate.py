"""Invariant Gate : « Recevoir n'est pas Accepter ».

Un événement issu d'un espace volatil ne modifie le registre canonique Γ que
s'il satisfait I₁–I₅. Le registre est une chaîne Γ du socle de preuve
(socle_preuve.gamma) : un seul format dans tout le dépôt, témoignable.

Chaque verdict porte un code stable. Avec un journal des décisions, la porte
inscrit aussi ses refus : le système prouve ce qu'il a refusé, pas seulement
ce qu'il a accepté.
"""

import enum
import hashlib
import hmac
import os
import time
from dataclasses import dataclass
from typing import Callable, Collection, NamedTuple

from socle_preuve.gamma import Chaine, ChaineRompue, TeteObsolete, lire_blocs


def sign(payload: bytes, key: bytes | None = None) -> str:
    """SHA-256 du payload ; HMAC-SHA-256 si une clé est fournie.

    Sans clé, I₂ ne prouve que l'intégrité (n'importe qui peut recalculer le
    hachage). La provenance exige la clé.
    """
    if key is None:
        return hashlib.sha256(payload).hexdigest()
    return hmac.new(key, payload, hashlib.sha256).hexdigest()


@dataclass(frozen=True)
class Event:
    event_id: str
    agent_id: str
    ledger_id: str
    payload: bytes
    signature_hash: str
    expected_state_hash: str


class Invariant(enum.Enum):
    I1_IDENTITY = "I1"
    I2_PROVENANCE = "I2"
    I3_IDEMPOTENCE = "I3"
    I4_OCC = "I4"
    I5_SUBSTRATE = "I5"


class Verdict(NamedTuple):
    accepted: bool            # l'événement est conforme
    committed: bool           # Γ a avancé (faux pour un rejeu idempotent)
    failed: Invariant | None = None
    code: str = "invariants_ok"   # identifiant stable, consommé par tests et journaux
    reason: str = ""              # explication lisible


class Ledger:
    """Registre canonique Γ des transitions acceptées, au format socle_preuve.

    Bloc 0 : genèse, qui fixe l'identité du registre (I₁). Puis un bloc par
    événement accepté. L'état courant est la tête de la chaîne.
    """

    GENESE = "genese"
    EVENEMENT = "evenement"

    def __init__(self, ledger_id: str, path: str | os.PathLike, *, temoin=None):
        if not isinstance(ledger_id, str) or not ledger_id:
            raise ValueError("ledger_id doit être une chaîne non vide")
        self.ledger_id = ledger_id
        self.path = os.fspath(path)
        self._chaine = Chaine(self.path, temoin=temoin)
        if not self._blocs():
            try:
                self._chaine.inscrire(self.GENESE, "OUVERT", "ouverture_registre",
                                      {"ledger_id": ledger_id}, si_tete="0" * 64)
            except TeteObsolete:
                pass  # un autre processus a créé la genèse : on la contrôle ci-dessous
        genese = self._blocs()[0]
        donnees = genese.get("donnees")
        if (genese["type"] != self.GENESE or not isinstance(donnees, dict)
                or donnees.get("ledger_id") != ledger_id):
            raise ValueError(f"registre_etranger : {self.path} n'est pas le registre {ledger_id!r}")

    def _blocs(self) -> list[dict]:
        blocs, rapport = lire_blocs(self.path)
        if not rapport.integre:
            raise ChaineRompue(rapport)
        return blocs

    def _evenements(self) -> list[dict]:
        return [b for b in self._blocs() if b["type"] == self.EVENEMENT]

    def __len__(self) -> int:
        return len(self._evenements())

    @property
    def entries(self) -> tuple[dict, ...]:
        return tuple(self._evenements())

    @property
    def state_hash(self) -> str:
        return self._blocs()[-1]["hash"]

    def seen(self, event_id: str) -> str | None:
        for bloc in reversed(self._evenements()):
            if bloc["donnees"]["event_id"] == event_id:
                return bloc["donnees"]["signature_hash"]
        return None

    def commit(self, event: "Event") -> str:
        """Inscrit l'événement si la tête vaut toujours `expected_state_hash`.

        Lève TeteObsolete sinon : l'OCC est tranché sous le verrou d'écriture.
        """
        bloc = self._chaine.inscrire(
            self.EVENEMENT, "ACCEPTE", "invariants_ok",
            {"event_id": event.event_id, "agent_id": event.agent_id,
             "payload": event.payload.hex(), "signature_hash": event.signature_hash},
            si_tete=event.expected_state_hash)
        return bloc["hash"]


class Substrate:
    """Sonde I₅ : entropie noyau et horloge monotone."""

    ENTROPY_PATH = "/proc/sys/kernel/random/entropy_avail"

    def entropy_avail(self) -> int:
        try:
            with open(self.ENTROPY_PATH) as fh:
                return int(fh.read())
        except (OSError, ValueError):
            return 0

    def monotonic_ns(self) -> int:
        return time.monotonic_ns()


def _refus(invariant: Invariant, code: str, reason: str) -> Verdict:
    return Verdict(False, False, invariant, code, reason)


class InvariantGate:
    def __init__(
        self,
        ledger: Ledger,
        authorized: Collection[str],
        *,
        key: bytes | None = None,
        substrate: Substrate | None = None,
        on_reject: Callable[[Event, Verdict], None] | None = None,
        journal: Chaine | None = None,
    ):
        """`journal` : chaîne Γ où inscrire chaque verdict, refus compris."""
        self.ledger = ledger
        self.authorized = frozenset(authorized)
        self.key = key
        self.substrate = substrate or Substrate()
        self.on_reject = on_reject
        self.journal = journal
        self._last_ns: int | None = None
        self.quarantined: set[str] = set()

    def quarantine(self, agent_id: str) -> None:
        self.quarantined.add(agent_id)

    def release(self, agent_id: str) -> None:
        self.quarantined.discard(agent_id)

    def _check(self, e: Event) -> Verdict:
        if e.ledger_id != self.ledger.ledger_id:
            return _refus(Invariant.I1_IDENTITY, "registre_etranger",
                          "identité de registre étrangère")
        if e.agent_id in self.quarantined:
            return _refus(Invariant.I1_IDENTITY, "agent_en_quarantaine",
                          f"agent en quarantaine : {e.agent_id}")
        if e.agent_id not in self.authorized:
            self.quarantined.add(e.agent_id)
            return _refus(Invariant.I1_IDENTITY, "agent_non_autorise",
                          f"agent non autorisé : {e.agent_id}")

        if not hmac.compare_digest(sign(e.payload, self.key), e.signature_hash):
            return _refus(Invariant.I2_PROVENANCE, "signature_invalide",
                          "signature SHA-256 invalide")

        known = self.ledger.seen(e.event_id)
        if known is not None:
            if known == e.signature_hash:
                return Verdict(True, False, None, "rejeu_idempotent",
                               "rejeu idempotent : déjà appliqué")
            return _refus(Invariant.I3_IDEMPOTENCE, "event_id_reutilise",
                          "event_id réutilisé avec un contenu différent")

        if e.expected_state_hash != self.ledger.state_hash:
            return _refus(Invariant.I4_OCC, "etat_perime", "expected_state_hash périmé")

        now = self.substrate.monotonic_ns()
        last, self._last_ns = self._last_ns, now
        if self.substrate.entropy_avail() <= 0:
            return _refus(Invariant.I5_SUBSTRATE, "entropie_nulle", "entropie noyau nulle")
        if last is not None and now <= last:
            return _refus(Invariant.I5_SUBSTRATE, "horloge_figee",
                          "horloge monotone figée ou régressive")

        try:
            self.ledger.commit(e)
        except TeteObsolete:
            return _refus(Invariant.I4_OCC, "etat_perime",
                          "la tête de Γ a avancé pendant l'admission")
        return Verdict(True, True)

    def _inscrire(self, e: Event, v: Verdict) -> None:
        decision = "ACCEPTE" if v.committed else ("REJEU" if v.accepted else "REJETE")
        self.journal.inscrire("admission", decision, v.code, {
            "event_id": e.event_id,
            "agent_id": e.agent_id,
            "ledger_id": e.ledger_id,
            "invariant": v.failed.value if v.failed else None,
            "payload_sha256": hashlib.sha256(e.payload).hexdigest(),  # l'empreinte, pas le contenu
        })

    def admit(self, event: Event) -> Verdict:
        verdict = self._check(event)
        if self.journal is not None:
            self._inscrire(event, verdict)
        if not verdict.accepted and self.on_reject is not None:
            self.on_reject(event, verdict)
        return verdict
