import math
import os
import sys
import tempfile
import time
import unittest

from rinv import (ChannelState, Event, FrameError, Invariant, InvariantGate, Ledger,
                  Supervisor, VoidMonitor, beat, decode, diagnose, efficiency, encode, infra_load,
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
        # CRC-16/X-25("123456789") = 0x906E, valeur de contrôle du catalogue
        from rinv.frame import _crc
        self.assertEqual(_crc(b"123456789"), 0x906E)

    def test_fcs_emitted_low_byte_first(self):
        from rinv.frame import _crc
        frame = encode(b"abc")
        self.assertEqual(frame[-2:], _crc(frame[1:-2]).to_bytes(2, "little"))

    def test_error_codes_are_stable(self):
        frame = encode(b"abc")
        cases = {"trame_tronquee": frame[:4], "fanion_absent": b"\x00" + frame[1:],
                 "longueur_incoherente": frame + b"\0",
                 "crc_invalide": frame[:-1] + bytes([frame[-1] ^ 1])}
        for code, bad in cases.items():
            with self.assertRaises(FrameError) as ctx:
                decode(bad)
            self.assertEqual(ctx.exception.code, code)
        with self.assertRaises(FrameError) as ctx:
            encode(bytes(0x10000))
        self.assertEqual(ctx.exception.code, "payload_trop_long")

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
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.ledger = Ledger("Γ", os.path.join(self.tmp.name, "registre.jsonl"))
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
        self.assertEqual(v, (True, True, None, "invariants_ok", ""))
        self.assertEqual(len(self.ledger), 1)
        self.assertNotEqual(self.ledger.state_hash, h0)
        self.assertEqual(self.rejects, [])

    def test_i1_identity(self):
        self.assertRejected(self.event(ledger_id="Γ'"), Invariant.I1_IDENTITY)
        self.assertRejected(self.event(agent_id="mallory"), Invariant.I1_IDENTITY)

    def test_unauthorized_actor_is_quarantined(self):
        self.assertRejected(self.event(agent_id="mallory"), Invariant.I1_IDENTITY)
        self.assertIn("mallory", self.gate.quarantined)

    def test_quarantined_agent_is_refused_until_released(self):
        self.gate.quarantine("alpha")
        self.assertRejected(self.event(), Invariant.I1_IDENTITY)
        self.gate.release("alpha")
        self.assertTrue(self.gate.admit(self.event()).committed)

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

    def test_verdict_codes_are_stable(self):
        self.assertEqual(self.gate.admit(self.event(ledger_id="Γ'")).code, "registre_etranger")
        self.assertEqual(self.gate.admit(self.event(agent_id="m")).code, "agent_non_autorise")
        self.assertEqual(self.gate.admit(self.event(agent_id="m")).code, "agent_en_quarantaine")
        self.assertEqual(self.gate.admit(self.event(signature_hash="x")).code, "signature_invalide")
        stale = self.event("b")
        self.assertEqual(self.gate.admit(self.event("a")).code, "invariants_ok")
        self.assertEqual(self.gate.admit(self.event("a")).code, "rejeu_idempotent")
        self.assertEqual(self.gate.admit(self.event("a", payload=b"y")).code, "event_id_reutilise")
        self.assertEqual(self.gate.admit(stale).code, "etat_perime")
        self.sub.entropy = 0
        self.assertEqual(self.gate.admit(self.event("c")).code, "entropie_nulle")
        self.sub.entropy, self.sub.step = 1, 0
        self.assertEqual(self.gate.admit(self.event("d")).code, "horloge_figee")

    def test_ledger_is_a_socle_preuve_chain_with_identity_genesis(self):
        from socle_preuve.gamma import lire_blocs, verifier_chaine
        self.gate.admit(self.event())
        blocs, rapport = lire_blocs(self.ledger.path)
        self.assertTrue(rapport.integre)
        self.assertEqual([b["type"] for b in blocs], ["genese", "evenement"])
        self.assertEqual(blocs[0]["donnees"], {"ledger_id": "Γ"})
        self.assertEqual(self.ledger.state_hash, verifier_chaine(self.ledger.path).tete)
        self.assertEqual(oct(os.stat(self.ledger.path).st_mode & 0o777), "0o600")

    def test_foreign_ledger_file_is_refused(self):
        with self.assertRaisesRegex(ValueError, "registre_etranger"):
            Ledger("Δ", self.ledger.path)

    def test_occ_race_is_decided_under_the_write_lock(self):
        """Un autre écrivain passe entre le contrôle I₄ et l'écriture : refus, pas de fourche."""
        rival = Ledger("Γ", self.ledger.path)
        rival_event = self.event("rival")
        sub = self.sub

        class Race(FakeSubstrate):
            def monotonic_ns(inner):  # appelé après I₄, avant le commit
                rival.commit(rival_event)
                return sub.monotonic_ns()

        gate = InvariantGate(self.ledger, {"alpha"}, substrate=Race())
        v = gate.admit(self.event("mien"))
        self.assertEqual((v.failed, v.code), (Invariant.I4_OCC, "etat_perime"))
        self.assertEqual([b["donnees"]["event_id"] for b in self.ledger.entries], ["rival"])

    def test_decisions_journal_records_refusals_and_acceptances(self):
        from socle_preuve.gamma import Chaine, lire_blocs
        journal = Chaine(os.path.join(self.tmp.name, "decisions.jsonl"))
        gate = InvariantGate(self.ledger, {"alpha"}, substrate=self.sub, journal=journal)
        secret_payload = b"contenu-sensible"
        gate.admit(self.event("a"))
        gate.admit(self.event("a"))
        gate.admit(self.event("b", agent_id="mallory", payload=secret_payload,
                              signature_hash=sign(secret_payload)))
        blocs, rapport = lire_blocs(journal.chemin)
        self.assertTrue(rapport.integre)
        self.assertEqual([(b["decision"], b["raison"]) for b in blocs],
                         [("ACCEPTE", "invariants_ok"), ("REJEU", "rejeu_idempotent"),
                          ("REJETE", "agent_non_autorise")])
        self.assertEqual(blocs[2]["donnees"]["invariant"], "I1")
        with open(journal.chemin, "rb") as fh:
            self.assertNotIn(secret_payload, fh.read())  # l'empreinte, jamais le contenu


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

    def test_quarantine_and_purge_are_journaled(self):
        from socle_preuve.gamma import Chaine, lire_blocs
        journal = Chaine(os.path.join(self.tmp.name, "decisions.jsonl"))
        self.mon = VoidMonitor(clock=lambda: self.now, journal=journal)
        p = self.pipe("mallory")
        self.mon.quarantine(p, "agent_non_autorise")
        self.now = 15 * self.S
        self.mon.sweep()
        blocs, rapport = lire_blocs(journal.chemin)
        self.assertTrue(rapport.integre)
        self.assertEqual([(b["decision"], b["raison"]) for b in blocs],
                         [("QUARANTAINE", "quarantaine_douce"), ("PURGE", "silence_depasse")])
        self.assertEqual(blocs[1]["donnees"], {"canal": p, "motif": "agent_non_autorise",
                                               "silence_ns": 15 * self.S})

    def test_gate_rejection_feeds_quarantine(self):
        p = self.pipe("shm-frame")
        ledger = Ledger("Γ", os.path.join(self.tmp.name, "registre.jsonl"))
        gate = InvariantGate(ledger, {"alpha"}, substrate=FakeSubstrate(),
                             on_reject=lambda e, v: self.mon.quarantine(p, v.reason))
        gate.admit(Event("e", "alpha", "Γ", b"x", "bad", ledger.state_hash))
        self.assertIs(self.mon.state(p), ChannelState.SOFT_QUARANTINE)
        self.assertEqual(len(ledger), 0)


class FakeHandle:
    def __init__(self):
        self.code, self.killed = None, False

    def poll(self):
        return self.code

    def kill(self):
        self.killed, self.code = True, -9

    def wait(self, timeout=None):
        return self.code


class SutureTest(unittest.TestCase):
    MS = 1_000_000

    def setUp(self):
        self.now = 0
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.spawned = []

        def spawn(name, hb):
            self.spawned.append(name)
            return FakeHandle()

        self.names = [f"P{k}" for k in range(1, 9)]
        self.sup = Supervisor(self.names, spawn, directory=self.tmp.name,
                              timeout_ns=100 * self.MS, clock=lambda: self.now)

    def beat_all(self, skip=()):
        for n in self.names:
            if n not in skip:
                beat(self.sup.heartbeat_path(n), self.now)

    def test_full_cohesion(self):
        self.now = 50 * self.MS
        self.beat_all()
        self.assertEqual(self.sup.cohesion(), 1.0)
        self.assertEqual(self.sup.suture(), [])

    def test_silent_node_drops_cohesion_then_is_sutured(self):
        self.now = 50 * self.MS
        self.beat_all()
        self.now = 120 * self.MS
        self.beat_all(skip={"P4"})
        self.now = 150 * self.MS  # dernier battement de P4 : il y a 100 ms
        self.assertEqual(self.sup.cohesion(), 0.875)
        old = self.sup._nodes["P4"].handle
        self.assertEqual(self.sup.suture(), ["P4"])
        self.assertTrue(old.killed)
        self.assertEqual(self.sup.generation("P4"), 1)
        self.assertEqual(self.sup.generation("P3"), 0)
        self.assertFalse(os.path.exists(self.sup.heartbeat_path("P4")))
        self.assertEqual(self.sup.cohesion(), 1.0)  # délai de grâce du remplaçant
        self.assertEqual(self.spawned.count("P4"), 2)

    def test_suture_is_journaled_with_its_cause(self):
        from socle_preuve.gamma import Chaine, lire_blocs
        journal = Chaine(os.path.join(self.tmp.name, "decisions.jsonl"))
        self.sup.journal = journal
        self.beat_all()
        self.sup._nodes["P2"].handle.code = 1          # mort
        self.now = 150 * self.MS
        self.beat_all(skip={"P2", "P5"})               # P5 vivant mais muet
        self.sup.suture()
        blocs, _ = lire_blocs(journal.chemin)
        self.assertEqual(sorted((b["donnees"]["noeud"], b["raison"]) for b in blocs),
                         [("P2", "processus_mort"), ("P5", "battement_muet")])

    def test_exited_node_detected_without_waiting_for_timeout(self):
        self.beat_all()
        self.sup._nodes["P7"].handle.code = 1
        self.assertEqual(self.sup.cohesion(), 0.875)
        self.assertEqual(self.sup.suture(), ["P7"])

    def test_replacement_that_never_beats_is_sutured_again(self):
        self.sup._nodes["P1"].handle.code = 1
        self.sup.suture()
        self.now = 100 * self.MS
        self.beat_all(skip={"P1"})
        self.assertEqual(self.sup.suture(), ["P1"])
        self.assertEqual(self.sup.generation("P1"), 2)

    def test_stale_heartbeat_file_does_not_predate_birth(self):
        beat(self.sup.heartbeat_path("P2"), -10**12)
        self.assertTrue(self.sup.alive("P2"))

    def test_real_processes(self):
        import subprocess
        worker = ("import sys,time;sys.path.insert(0,%r);from rinv import beat\n"
                  "while True: beat(sys.argv[1]); time.sleep(0.02)" % os.getcwd())
        spawn = lambda name, hb: subprocess.Popen([sys.executable, "-c", worker, hb])
        sup = Supervisor(["A", "B", "C", "D"], spawn, directory=self.tmp.name,
                         timeout_ns=5_000 * self.MS)
        self.addCleanup(sup.shutdown)
        self.assertEqual(sup.cohesion(), 1.0)
        victim = sup._nodes["C"].handle
        victim.kill()
        victim.wait()
        self.assertEqual(sup.cohesion(), 0.75)
        self.assertEqual(sup.suture(), ["C"])
        self.assertEqual(sup.cohesion(), 1.0)
        self.assertNotEqual(sup._nodes["C"].handle.pid, victim.pid)
        deadline = time.monotonic() + 10
        while not os.path.exists(sup.heartbeat_path("C")):
            self.assertLess(time.monotonic(), deadline, "le remplaçant n'a jamais battu")
            time.sleep(0.01)


if __name__ == "__main__":
    unittest.main()
