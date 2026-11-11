"""Void Monitor : quarantaine douce puis purge des tubes volatils (/dev/shm)."""

import enum
import os
import stat
import time
from dataclasses import dataclass
from typing import Callable

PURGE_AFTER_NS = 15 * 1_000_000_000


class ChannelState(enum.Enum):
    LIVE = "LIVE"
    SOFT_QUARANTINE = "SOFT_QUARANTINE"
    PURGED = "PURGED"


@dataclass
class _Channel:
    state: ChannelState
    last_valid_ns: int
    reason: str = ""


class VoidMonitor:
    """Surveille des fichiers-canaux ; purge ceux restés muets ou incohérents.

    Le temporisateur mesure le temps écoulé depuis la dernière activité *valide*
    (`touch`). Une quarantaine ne le réarme pas.
    """

    def __init__(
        self,
        purge_after_ns: int = PURGE_AFTER_NS,
        clock: Callable[[], int] = time.monotonic_ns,
    ):
        self.purge_after_ns = purge_after_ns
        self._clock = clock
        self._channels: dict[str, _Channel] = {}

    def watch(self, path: str | os.PathLike) -> None:
        self._channels[os.fspath(path)] = _Channel(ChannelState.LIVE, self._clock())

    def state(self, path: str | os.PathLike) -> ChannelState:
        return self._channels[os.fspath(path)].state

    def reason(self, path: str | os.PathLike) -> str:
        return self._channels[os.fspath(path)].reason

    def _live(self, path) -> _Channel:
        ch = self._channels[os.fspath(path)]
        if ch.state is ChannelState.PURGED:
            raise ValueError(f"canal purgé : {os.fspath(path)}")
        return ch

    def touch(self, path: str | os.PathLike) -> None:
        """Une trame valide a transité : le canal redevient LIVE."""
        ch = self._live(path)
        ch.state, ch.last_valid_ns, ch.reason = ChannelState.LIVE, self._clock(), ""

    def quarantine(self, path: str | os.PathLike, reason: str) -> None:
        ch = self._live(path)
        ch.state, ch.reason = ChannelState.SOFT_QUARANTINE, reason

    def sweep(self) -> list[str]:
        """Purge les canaux dont le silence dépasse le seuil. Retourne leurs chemins."""
        now, purged = self._clock(), []
        for path, ch in self._channels.items():
            if ch.state is ChannelState.PURGED:
                continue
            if now - ch.last_valid_ns >= self.purge_after_ns:
                _shred(path)
                ch.state = ChannelState.PURGED
                ch.reason = ch.reason or "silence"
                purged.append(path)
        return purged


def _shred(path: str) -> None:
    """Écrase, tronque et supprime un fichier régulier, sans suivre les liens."""
    try:
        fd = os.open(path, os.O_WRONLY | os.O_NOFOLLOW)
    except FileNotFoundError:
        return
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            raise ValueError(f"refus de purger un fichier non régulier : {path}")
        remaining, zeros = st.st_size, bytes(65536)
        while remaining > 0:
            remaining -= os.write(fd, zeros[:remaining])
        os.fsync(fd)
        os.ftruncate(fd, 0)
    finally:
        os.close(fd)
    os.unlink(path)
