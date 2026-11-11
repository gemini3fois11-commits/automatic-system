import math
import os
import sys
import tempfile
import unittest

from rinv import (ChannelState, Event, FrameError, Invariant, InvariantGate, Ledger,
                  VoidMonitor, decode, diagnose, efficiency, encode, infra_load,
                  inverse_sum, sign, torus)


class FakeSubstrate:
    def __init__(self, entropy=256):
        self.entropy, self.ns, self.step = entropy, 0, 1

    def entropy_avail(self):
        return self.entropy

    def monotonic_ns(self):
        self.ns += self.step
        return self.ns


class FrameTest(unittest.TestCase):
    def test_roundtrip(self):
        for payload in (b"", b"x", bytes(range(256)) * 4):
            self.assertEqual(decode(encode(payload)), payload)

    def test_known_crc(self):
        # CRC-16/CCITT-FALSE("123456789") = 0x29B1
        from rinv.frame import _crc
        self.assertEqual(_crc(b"123456789"), 0x29B1)

    def test_every_single_bit_flip_is_rejected(self):
        frame = encode(b"HULTIMUGO")
        for i in range(len(frame) * 8):
            bad = bytearray(frame)
            bad[i // 8] ^= 1 << (i % 8)
            with self.assertRaises(FrameError):
                decode(bytes(bad))

    def test_truncated_and_trailing(self):
        frame = encode(b"abc")
        for bad in (frame[:-1], frame + b"\0", b"", b"\x7e"):
            with self.assertRaises(FrameError):
                decode(bad)


class StabilityTest(unittest.TestCase):
    def test_nominal_888(self):
        self.assertEqual(inverse_sum([1.0] * 888), 888.0)

    def test_collapse_dominates_where_mean_hides_it(self):
        nodes = {f"n{k}": 1.0 for k in range(888)}
        nodes["n421"] = 1e-6
        self.assertGreater(sum(nodes.values()) / 888, 0.998)  # moyenne trompeuse
        d = diagnose(nodes)
        self.assertEqual(d.weakest, "n421")
        self.assertGreater(d.excess, 999_000)

    def test_dead_node_is_infinite(self):
        self.assertEqual(inverse_sum([1.0, 0.0, 1.0]), math.inf)

    def test_out_of_range(self):
        for bad in (-0.1, 1.1, math.nan):
            with self.assertRaises(ValueError):
                inverse_sum([bad])

    def test_empty(self):
        self.assertEqual(diagnose({}).weakest, None)

    def test_infra_load(self):
        # A=2, M=1, D=3 constants sur [0, 10] avec α,β,γ = 1,2,3 → (2+2+9)·10
        samples = [(0, 2, 1, 3), (4, 2, 1, 3), (10, 2, 1, 3)]
        self.assertAlmostEqual(infra_load(samples, 1, 2, 3), 130.0)
        self.assertAlmostEqual(efficiency(260.0, 130.0), 2.0)
        with self.assertRaises(ValueError):
            infra_load([(1, 0, 0, 0), (1, 0, 0, 0)])


class TctcTest(unittest.TestCase):
    def test_deep_tail_recursion_does_not_overflow(self):
        @torus()
        def total(n, acc=0):
            return acc if n == 0 else total(n - 1, acc + n)

        n = 100_000
        self.assertGreater(n, sys.getrecursionlimit())
        self.assertEqual(total(n), n * (n + 1) // 2)
        self.assertGreater(total.folds, 0)

    def test_fold_count_matches_modulus(self):
        @torus(rho_c=10)
        def down(n):
            return "ok" if n == 0 else down(n - 1)

        self.assertEqual(down(95), "ok")
        self.assertEqual(down.folds, 95 // 11)  # 1 cadre d'entrée + 10 de profondeur
        self.assertEqual(down(5), "ok")
        self.assertEqual(down.folds, 0)

    def test_exceptions_propagate_and_state_resets(self):
        @torus(rho_c=5)
        def boom(n):
            if n == 0:
                raise KeyError("fond")
            return boom(n - 1)

        with self.assertRaises(KeyError):
            boom(50)
        with self.assertRaises(KeyError):
            boom(50)

    def test_kwargs_reinjected(self):
        @torus(rho_c=3)
        def f(n, *, acc):
            return acc if n == 0 else f(n - 1, acc=acc + [n])

        self.assertEqual(f(8, acc=[]), [8, 7, 6, 5, 4, 3, 2, 1])


class GateTest(unittest.TestCase):
    def setUp(self):
        self.ledger = Ledger("Γ")
        self.sub = FakeSubstrate()
        self.rejects = []
        self.gate = InvariantGate(self.ledger, {"alpha"}, substrate=self.sub,
                                  on_reject=lambda e, v: self.rejects.append(v))

    def event(self, eid="e1", payload=b"set x=1", **over):
        fields = dict(event_id=eid, agent_id="alpha", ledger_id="Γ", payload=payload,
                      signature_hash=sign(payload),
                      expected_state_hash=self.ledger.state_hash)
        fields.update(over)
        return Event(**fields)

    def assertRejected(self, event, invariant):
        before = (len(self.ledger), self.ledger.state_hash)
        v = self.gate.admit(event)
        self.assertFalse(v.accepted)
        self.assertFalse(v.committed)
        self.assertIs(v.failed, invariant)
        self.assertEqual((len(self.ledger), self.ledger.state_hash), before)
        self.assertIs(self.rejects[-1], v)

    def test_valid_event_commits(self):
        h0 = self.ledger.state_hash
        v = self.gate.admit(self.event())
        self.assertEqual(v, (True, True, None, ""))
        self.assertEqual(len(self.ledger), 1)
        self.assertNotEqual(self.ledger.state_hash, h0)
        self.assertEqual(self.rejects, [])

    def test_i1_identity(self):
        self.assertRejected(self.event(ledger_id="Γ'"), Invariant.I1_IDENTITY)
        self.assertRejected(self.event(agent_id="mallory"), Invariant.I1_IDENTITY)

    def test_i2_tampered_payload(self):
        self.assertRejected(self.event(signature_hash=sign(b"autre")), Invariant.I2_PROVENANCE)

    def test_i2_hmac_key(self):
        gate = InvariantGate(self.ledger, {"alpha"}, key=b"k", substrate=self.sub)
        self.assertIs(gate.admit(self.event()).failed, Invariant.I2_PROVENANCE)
        ok = self.event(signature_hash=sign(b"set x=1", b"k"))
        self.assertTrue(gate.admit(ok).committed)

    def test_i3_replay_is_noop(self):
        e = self.event()
        self.gate.admit(e)
        h = self.ledger.state_hash
        v = self.gate.admit(e)  # expected_state_hash désormais périmé : I₃ prime sur I₄
        self.assertTrue(v.accepted)
        self.assertFalse(v.committed)
        self.assertEqual((len(self.ledger), self.ledger.state_hash), (1, h))

    def test_i3_event_id_reuse_with_other_content(self):
        self.gate.admit(self.event())
        self.assertRejected(self.event(payload=b"set x=2"), Invariant.I3_IDEMPOTENCE)

    def test_i4_stale_branch(self):
        a, b = self.event("a"), self.event("b")  # deux écrivains sur le même état
        self.assertTrue(self.gate.admit(a).committed)
        self.assertRejected(b, Invariant.I4_OCC)

    def test_i5_no_entropy(self):
        self.sub.entropy = 0
        self.assertRejected(self.event(), Invariant.I5_SUBSTRATE)

    def test_i5_frozen_clock(self):
        self.assertTrue(self.gate.admit(self.event("a")).committed)
        self.sub.step = 0
        self.assertRejected(self.event("b"), Invariant.I5_SUBSTRATE)

    def test_real_substrate(self):
        gate = InvariantGate(self.ledger, {"alpha"})
        self.assertTrue(gate.admit(self.event("a")).committed)
        self.assertTrue(gate.admit(self.event("b")).committed)

    def test_durable_ledger_reload_and_tamper_detection(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "gamma.jsonl")
            self.ledger = Ledger("Γ", path)
            gate = InvariantGate(self.ledger, {"alpha"}, substrate=self.sub)
            for eid in ("a", "b", "c"):
                self.assertTrue(gate.admit(self.event(eid)).committed)

            reloaded = Ledger("Γ", path)
            self.assertEqual(reloaded.state_hash, self.ledger.state_hash)
            self.assertEqual(len(reloaded), 3)
            self.assertIsNotNone(reloaded.seen("b"))

            with open(path, encoding="utf-8") as fh:
                lines = fh.read().splitlines()
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("\n".join([lines[0], lines[2]]) + "\n")
            with self.assertRaises(ValueError):
                Ledger("Γ", path)


class VoidMonitorTest(unittest.TestCase):
    S = 1_000_000_000

    def setUp(self):
        self.now = 0
        self.mon = VoidMonitor(clock=lambda: self.now)
        self.tmp = tempfile.TemporaryDirectory(
            dir="/dev/shm" if os.path.isdir("/dev/shm") else None)
        self.addCleanup(self.tmp.cleanup)

    def pipe(self, name, data=b"trame-corrompue"):
        path = os.path.join(self.tmp.name, name)
        with open(path, "wb") as fh:
            fh.write(data)
        self.mon.watch(path)
        return path

    def test_silence_purges_at_15s(self):
        p = self.pipe("ghost")
        self.now = 15 * self.S - 1
        self.assertEqual(self.mon.sweep(), [])
        self.assertTrue(os.path.exists(p))
        self.now = 15 * self.S
        self.assertEqual(self.mon.sweep(), [p])
        self.assertFalse(os.path.exists(p))
        self.assertIs(self.mon.state(p), ChannelState.PURGED)
        self.assertEqual(self.mon.sweep(), [])

    def test_activity_rearms_and_clears_quarantine(self):
        p = self.pipe("afsk")
        self.now = 10 * self.S
        self.mon.quarantine(p, "entropie nulle")
        self.assertIs(self.mon.state(p), ChannelState.SOFT_QUARANTINE)
        self.mon.touch(p)
        self.assertIs(self.mon.state(p), ChannelState.LIVE)
        self.now = 24 * self.S
        self.assertEqual(self.mon.sweep(), [])
        self.now = 25 * self.S
        self.assertEqual(self.mon.sweep(), [p])

    def test_quarantine_does_not_rearm(self):
        p = self.pipe("q")
        self.now = 14 * self.S
        self.mon.quarantine(p, "horodatage")
        self.now = 15 * self.S
        self.assertEqual(self.mon.sweep(), [p])
        self.assertEqual(self.mon.reason(p), "horodatage")
        with self.assertRaises(ValueError):
            self.mon.touch(p)

    def test_content_is_overwritten_before_unlink(self):
        p = self.pipe("secret", b"S" * 100_000)
        fd = os.open(p, os.O_RDONLY)  # un lecteur garde l'inode ouvert
        self.addCleanup(os.close, fd)
        self.now = 15 * self.S
        self.mon.sweep()
        self.assertEqual(os.fstat(fd).st_size, 0)

    def test_symlink_is_not_followed(self):
        target = os.path.join(self.tmp.name, "canon")
        with open(target, "wb") as fh:
            fh.write(b"registre")
        link = os.path.join(self.tmp.name, "lien")
        os.symlink(target, link)
        self.mon.watch(link)
        self.now = 15 * self.S
        with self.assertRaises(OSError):
            self.mon.sweep()
        with open(target, "rb") as fh:
            self.assertEqual(fh.read(), b"registre")

    def test_missing_file_is_fine(self):
        p = self.pipe("gone")
        os.unlink(p)
        self.now = 15 * self.S
        self.assertEqual(self.mon.sweep(), [p])

    def test_gate_rejection_feeds_quarantine(self):
        p = self.pipe("shm-frame")
        ledger = Ledger("Γ")
        gate = InvariantGate(ledger, {"alpha"}, substrate=FakeSubstrate(),
                             on_reject=lambda e, v: self.mon.quarantine(p, v.reason))
        gate.admit(Event("e", "alpha", "Γ", b"x", "bad", ledger.state_hash))
        self.assertIs(self.mon.state(p), ChannelState.SOFT_QUARANTINE)
        self.assertEqual(len(ledger), 0)


if __name__ == "__main__":
    unittest.main()
