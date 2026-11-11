"""Invariant Gate : « Recevoir n'est pas Accepter ».

Un événement issu d'un espace volatil ne modifie le registre canonique Γ que
s'il satisfait I₁–I₅. Le registre est append-only et chaîné par hachage.
"""

import enum
import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass
from typing import Callable, Collection, NamedTuple


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
    reason: str = ""


class Ledger:
    """Registre canonique Γ : append-only, chaîné, optionnellement durable."""

    def __init__(self, ledger_id: str, path: str | os.PathLike | None = None):
        self.ledger_id = ledger_id
        self.path = path
        self.state_hash = hashlib.sha256(ledger_id.encode()).hexdigest()
        self._entries: list[dict] = []
        self._seen: dict[str, str] = {}  # event_id -> signature_hash
        if path is not None and os.path.exists(path):
            self._replay(path)

    def __len__(self) -> int:
        return len(self._entries)

    @property
    def entries(self) -> tuple[dict, ...]:
        return tuple(self._entries)

    def seen(self, event_id: str) -> str | None:
        return self._seen.get(event_id)

    def _next_hash(self, event_id: str, signature_hash: str) -> str:
        return hashlib.sha256(
            f"{self.state_hash}|{event_id}|{signature_hash}".encode()
        ).hexdigest()

    def _append(self, entry: dict) -> None:
        self._entries.append(entry)
        self._seen[entry["event_id"]] = entry["signature_hash"]
        self.state_hash = entry["state_hash"]

    def _replay(self, path) -> None:
        with open(path, encoding="utf-8") as fh:
            for lineno, line in enumerate(fh, 1):
                entry = json.loads(line)
                expected = self._next_hash(entry["event_id"], entry["signature_hash"])
                if entry["prev_hash"] != self.state_hash or entry["state_hash"] != expected:
                    raise ValueError(f"{path}:{lineno} : chaîne de hachage rompue")
                self._append(entry)

    def commit(self, event: Event) -> str:
        entry = {
            "seq": len(self._entries),
            "event_id": event.event_id,
            "agent_id": event.agent_id,
            "payload": event.payload.hex(),
            "signature_hash": event.signature_hash,
            "prev_hash": self.state_hash,
            "state_hash": self._next_hash(event.event_id, event.signature_hash),
        }
        if self.path is not None:
            with open(self.path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry, sort_keys=True) + "\n")
                fh.flush()
                os.fsync(fh.fileno())
        self._append(entry)
        return self.state_hash


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


class InvariantGate:
    def __init__(
        self,
        ledger: Ledger,
        authorized: Collection[str],
        *,
        key: bytes | None = None,
        substrate: Substrate | None = None,
        on_reject: Callable[[Event, Verdict], None] | None = None,
    ):
        self.ledger = ledger
        self.authorized = frozenset(authorized)
        self.key = key
        self.substrate = substrate or Substrate()
        self.on_reject = on_reject
        self._last_ns: int | None = None

    def _check(self, e: Event) -> Verdict:
        if e.ledger_id != self.ledger.ledger_id:
            return Verdict(False, False, Invariant.I1_IDENTITY, "identité de registre étrangère")
        if e.agent_id not in self.authorized:
            return Verdict(False, False, Invariant.I1_IDENTITY, f"agent non autorisé : {e.agent_id}")

        if not hmac.compare_digest(sign(e.payload, self.key), e.signature_hash):
            return Verdict(False, False, Invariant.I2_PROVENANCE, "signature SHA-256 invalide")

        known = self.ledger.seen(e.event_id)
        if known is not None:
            if known == e.signature_hash:
                return Verdict(True, False, None, "rejeu idempotent : déjà appliqué")
            return Verdict(False, False, Invariant.I3_IDEMPOTENCE,
                           "event_id réutilisé avec un contenu différent")

        if e.expected_state_hash != self.ledger.state_hash:
            return Verdict(False, False, Invariant.I4_OCC, "expected_state_hash périmé")

        now = self.substrate.monotonic_ns()
        last, self._last_ns = self._last_ns, now
        if self.substrate.entropy_avail() <= 0:
            return Verdict(False, False, Invariant.I5_SUBSTRATE, "entropie noyau nulle")
        if last is not None and now <= last:
            return Verdict(False, False, Invariant.I5_SUBSTRATE, "horloge monotone figée ou régressive")

        self.ledger.commit(e)
        return Verdict(True, True)

    def admit(self, event: Event) -> Verdict:
        verdict = self._check(event)
        if not verdict.accepted and self.on_reject is not None:
            self.on_reject(event, verdict)
        return verdict
