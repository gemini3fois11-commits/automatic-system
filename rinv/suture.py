"""Auto-Suture : un superviseur recoud la matrice quand un processus s'éteint.

Chaque nœud P_k prouve sa vie en écrivant l'horloge monotone dans un fichier de
battement (dans /dev/shm par défaut). Le superviseur mesure la cohésion
(nœuds vivants / nœuds attendus) et, pour chaque nœud muet ou mort, tue ce qu'il
en reste, purge son battement et relance un remplaçant.
"""

import os
import time
from dataclasses import dataclass
from typing import Callable, Iterable, Protocol

HEARTBEAT_TIMEOUT_NS = 1_000_000_000


class Handle(Protocol):
    """Sous-ensemble de subprocess.Popen dont le superviseur a besoin."""

    def poll(self) -> int | None: ...
    def kill(self) -> None: ...
    def wait(self, timeout: float | None = None) -> int: ...


def beat(path: str | os.PathLike, now_ns: int | None = None) -> None:
    """Signal de vie, côté nœud. Écriture atomique (rename)."""
    path = os.fspath(path)
    tmp = f"{path}.{os.getpid()}.tmp"
    with open(tmp, "w") as fh:
        fh.write(str(time.monotonic_ns() if now_ns is None else now_ns))
    os.replace(tmp, path)


@dataclass
class _Node:
    handle: Handle
    born_ns: int
    generation: int = 0


class Supervisor:
    def __init__(
        self,
        names: Iterable[str],
        spawn: Callable[[str, str], Handle],
        *,
        directory: str | os.PathLike = "/dev/shm",
        timeout_ns: int = HEARTBEAT_TIMEOUT_NS,
        clock: Callable[[], int] = time.monotonic_ns,
        journal=None,
    ):
        """`spawn(name, heartbeat_path)` lance un nœud et retourne son handle.
        `journal` : chaîne Γ où inscrire chaque suture."""
        self._spawn = spawn
        self.journal = journal
        self._dir = os.fspath(directory)
        self.timeout_ns = timeout_ns
        self._clock = clock
        self._nodes: dict[str, _Node] = {}
        for name in names:
            self._nodes[name] = _Node(spawn(name, self.heartbeat_path(name)), clock())
        if not self._nodes:
            raise ValueError("au moins un nœud est requis")

    def heartbeat_path(self, name: str) -> str:
        return os.path.join(self._dir, f"{name}.hb")

    def generation(self, name: str) -> int:
        return self._nodes[name].generation

    def _last_sign_of_life(self, name: str, node: _Node) -> int:
        """Dernier battement, ou la naissance tant que le nœud n'a pas encore battu."""
        try:
            with open(self.heartbeat_path(name)) as fh:
                return max(int(fh.read()), node.born_ns)
        except (OSError, ValueError):
            return node.born_ns

    def alive(self, name: str) -> bool:
        node = self._nodes[name]
        if node.handle.poll() is not None:
            return False
        return self._clock() - self._last_sign_of_life(name, node) < self.timeout_ns

    def cohesion(self) -> float:
        """Fraction de nœuds vivants : 7 sur 8 → 0,875."""
        return sum(self.alive(n) for n in self._nodes) / len(self._nodes)

    def suture(self) -> list[str]:
        """Remplace chaque nœud mort ou muet. Retourne les noms recousus."""
        sutured = []
        for name, node in self._nodes.items():
            if self.alive(name):
                continue
            mort = node.handle.poll() is not None
            if not mort:  # muet mais encore là : on l'achève
                node.handle.kill()
            node.handle.wait()
            try:
                os.unlink(self.heartbeat_path(name))
            except FileNotFoundError:
                pass
            node.handle = self._spawn(name, self.heartbeat_path(name))
            node.born_ns = self._clock()
            node.generation += 1
            sutured.append(name)
            if self.journal is not None:
                self.journal.inscrire("noeud", "SUTURE",
                                      "processus_mort" if mort else "battement_muet",
                                      {"noeud": name, "generation": node.generation})
        return sutured

    def shutdown(self) -> None:
        for name, node in self._nodes.items():
            if node.handle.poll() is None:
                node.handle.kill()
            node.handle.wait()
            try:
                os.unlink(self.heartbeat_path(name))
            except FileNotFoundError:
                pass
