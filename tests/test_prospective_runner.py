"""Fast virtual-clock scheduler rehearsals; no real sleeps, encrypted captures or AWS calls."""
import copy
import unittest
from datetime import datetime, timedelta, timezone
from research.catalog import canonical_sha256
from research.contracts import PROPOSAL_SHA256
from research.prospective_runner import DevelopmentSamplingRunner, CollectorAbort


class RunnerTests(unittest.TestCase):
    """Preserve the fixed cutoff and durable audit without returning live determinations."""

    def setUp(self):
        """Prepare a virtual pre-trigger reference, bounded plan and in-memory journal.

        Inputs:
            No external input; all clocks, evidence fingerprints and journal writes are synthetic.
        Outputs:
            None: Stores fake dependencies and a development plan; no real collection is performed.
        """
        self.base = datetime(2026, 1, 1, tzinfo=timezone.utc)
        self.now, self.drift = -20.0, 0.0
        self.calls, self.journal, self.waits = [], [], []
        self.plan = {"phase": "development", "kind": "development_sampling",
                     "proposal_sha256": PROPOSAL_SHA256, "run_id": "synthetic-run",
                     "collector_scope_sha256": "a"*64,
                     "max_clock_skew_seconds": 1,
                     "sampling": {"phase": "development", "trigger_at": self.stamp(0),
                         "closed_at": self.stamp(1810), "max_start_lateness_seconds": 2,
                         "max_response_seconds": 5, "max_anchor_age_seconds": 30,
                         "samples": [{"sample_id": "anchor", "offset_seconds": -20},
                                     {"sample_id": "middle", "offset_seconds": 60},
                                     {"sample_id": "last", "offset_seconds": 1790}]}}

    def stamp(self, seconds):
        """Produce an explicit synthetic UTC timestamp.

        Inputs:
            seconds: Offset relative to the declared synthetic trigger.
        Outputs:
            str: ISO timestamp; no external effects.
        """
        return (self.base+timedelta(seconds=seconds)).isoformat()

    def wall(self):
        """Read the simulated wall clock, including independently controlled drift.

        Inputs:
            No arguments; uses this fixture's virtual elapsed seconds and drift.
        Outputs:
            datetime: Aware synthetic clock; performs no system-clock read.
        """
        return self.base+timedelta(seconds=self.now+self.drift)

    def mono(self):
        """Read virtual monotonic elapsed seconds.

        Inputs:
            No arguments; uses this fixture's virtual elapsed time.
        Outputs:
            float: Synthetic monotonic value without a real clock dependency.
        """
        return self.now+10000

    def sleep(self, seconds):
        """Advance virtual time without sleeping the test process.

        Inputs:
            seconds: Requested wait interval from the scheduling loop.
        Outputs:
            None: Records the wait and advances both simulated clocks consistently.
        """
        self.waits.append(seconds)
        self.now += seconds

    def collect(self, sample_id):
        """Return a synthetic source fingerprint after a simulated two-second collection.

        Inputs:
            sample_id: Scheduled pseudonymous collection identifier.
        Outputs:
            dict: Success status and fake evidence identity; updates fixture timing/call history.
        """
        self.calls.append((sample_id, self.now))
        self.now += 2
        return {"status": "success", "evidence_sha256": canonical_sha256({"synthetic": sample_id})}

    def persist(self, record):
        """Simulate a trusted encrypted journal without writing a file or using a key.

        Inputs:
            record: Runner metadata copied into the in-memory fixture journal.
        Outputs:
            str: Synthetic receipt hash; this fake is not proof of encryption or persistence.
        """
        self.journal.append(copy.deepcopy(record))
        return canonical_sha256(record)

    def runner(self, collect=None, persist=None, sleeper=None):
        """Bind the explicit test dependencies to the current source-pinned plan.

        Inputs:
            collect: Optional synthetic collector override; None uses the normal fixture callback.
            persist: Optional synthetic journal override; None uses the normal in-memory journal.
            sleeper: Optional virtual wait override; None advances the fixture clock.
        Outputs:
            DevelopmentSamplingRunner: Unexecuted test runner with no production integrations.
        """
        return DevelopmentSamplingRunner(self.plan, canonical_sha256(self.plan), collect or self.collect,
                                         persist or self.persist, self.wall, self.mono, sleeper or self.sleep)

    def test_fixed_horizon_short_waits_and_delayed_summary(self):
        """Execute a full virtual horizon while returning only after planned administrative closure.

        Inputs:
            Normal synthetic schedule, two-second collections and virtual dependencies.
        Outputs:
            None: Asserts exact starts, short waits, immutable copied plan and closed readiness flags.
        """
        runner = self.runner()
        self.plan["run_id"] = "external-edit"
        result = runner.run()
        self.assertEqual(self.calls, [("anchor", -20), ("middle", 60), ("last", 1790)])
        self.assertGreaterEqual(self.now, 1810)
        self.assertTrue(all(0 < wait <= 60 for wait in self.waits))
        self.assertEqual(result["sampling_audit"]["cutoff_at"], self.stamp(1800))
        self.assertTrue(result["sampling_audit"]["acquisition_schedule_met"])
        self.assertEqual(self.journal[-1]["kind"], "run_closed")
        self.assertEqual(self.journal[-1]["prior_journal_receipts"], result["journal_receipts"][:-1])
        self.assertTrue(all(event["run_id"] == "synthetic-run" for event in self.journal))
        for key in ["trigger_verified", "provider_delivery_verified", "ml_ready", "formal_trial_authorized"]:
            self.assertFalse(result[key])
        with self.assertRaises(ValueError):
            runner.run()

    def test_late_launch_skips_missed_anchor(self):
        """Skip a missed pre-trigger target instead of collecting a replacement anchor.

        Inputs:
            Virtual launch at the trigger, after the anchor start deadline.
        Outputs:
            None: Asserts missing anchor remains explicit and later targets retain their times.
        """
        self.now = 0
        result = self.runner().run()
        self.assertEqual(result["skipped_samples"], ["anchor"])
        self.assertEqual(self.calls, [("middle", 60), ("last", 1790)])
        self.assertFalse(result["sampling_audit"]["acquisition_schedule_met"])

    def test_journal_lateness_and_overruns_do_not_shift_later_targets(self):
        """Count persistence delay and skip a missed target rather than shifting the schedule.

        Inputs:
            Separate virtual slow-journal and long-anchor collector cases.
        Outputs:
            None: Asserts skipped targets and unchanged later planned starts.
        """
        def slow_journal(record):
            """Consume synthetic start tolerance during durable journal handling.

            Inputs:
                record: Metadata selecting the anchor due event.
            Outputs:
                str: Fake journal receipt; may advance virtual time by three seconds.
            """
            if record["kind"] == "sample_due" and record["sample_id"] == "anchor":
                self.now += 3
            return self.persist(record)
        result = self.runner(persist=slow_journal).run()
        self.assertEqual(result["skipped_samples"], ["anchor"])
        self.assertEqual(self.calls, [("middle", 60), ("last", 1790)])
        self.setUp()
        def long_anchor(sample_id):
            """Simulate a callback running past the next scheduled target.

            Inputs:
                sample_id: Scheduled identifier selecting the anchor overrun.
            Outputs:
                dict: Fake source result; anchor advances virtual time by ninety seconds.
            """
            result = self.collect(sample_id)
            if sample_id == "anchor":
                self.now += 88
            return result
        result = self.runner(collect=long_anchor).run()
        self.assertEqual(result["skipped_samples"], ["middle"])
        self.assertEqual(self.calls[-1], ("last", 1790))

    def test_callback_overrun_does_not_extend_detection_cutoff(self):
        """Retain a callback returning after planned closure and preserve the original cutoff.

        Inputs:
            Synthetic collector whose last call lasts fifty seconds instead of two.
        Outputs:
            None: Asserts actual closure/late receipts are retained, not backdated or censored detections.
        """
        def slow(sample_id):
            """Advance virtual time through an uninterruptible synthetic collector call.

            Inputs:
                sample_id: Scheduled identifier used to select the overrun case.
            Outputs:
                dict: Synthetic source result; advances virtual time without IO.
            """
            result = self.collect(sample_id)
            if sample_id == "last":
                self.now += 48
            return result
        result = self.runner(collect=slow).run()
        self.assertEqual(result["actual_closed_at"], self.stamp(1840))
        self.assertEqual(result["sampling_audit"]["cutoff_at"], self.stamp(1800))
        self.assertEqual(result["sampling_audit"]["samples"][-1]["receipt"]["recorded_at"], self.stamp(1840))
        self.assertIn("received_after_horizon", result["sampling_audit"]["samples"][-1]["blockers"])

    def test_collector_exception_is_sanitized_and_audited(self):
        """Retain a failed invocation without copying exception text into evidence or summary.

        Inputs:
            Synthetic callback raising a recognizable private marker for one sample.
        Outputs:
            None: Asserts error receipt/journal and absence of the marker in retained metadata.
        """
        def failing(sample_id):
            """Raise a synthetic secret-shaped message without any real credential.

            Inputs:
                sample_id: Identifier choosing the simulated failure.
            Outputs:
                dict: Normal fake source result except at the failing sample, which raises.
            """
            if sample_id == "middle":
                raise RuntimeError("private-test-marker")
            return self.collect(sample_id)
        result = self.runner(collect=failing).run()
        self.assertEqual(result["receipts"][1]["status"], "error")
        self.assertNotIn("private-test-marker", repr((result, self.journal)))
        self.assertTrue(any(event["kind"] == "collector_failed" for event in self.journal))

    def test_journal_failure_aborts_before_collection(self):
        """Stop before source reads when the first durable-journal callback fails.

        Inputs:
            Synthetic persistence callback failing immediately.
        Outputs:
            None: Asserts no collector call or healthy completion marker.
        """
        def failing(record):
            """Simulate unavailable encrypted persistence.

            Inputs:
                record: Run event that cannot be durably retained.
            Outputs:
                None: Always raises OSError without touching disk.
            """
            raise OSError("synthetic journal unavailable")
        with self.assertRaises(OSError):
            self.runner(persist=failing).run()
        self.assertEqual(self.calls, [])

    def test_fatal_collector_scope_failure_stops_the_schedule(self):
        """Propagate a trusted native collector's fatal scope/identity guard failure.

        Inputs:
            Synthetic fatal callback, without any worker process or AWS operation.
        Outputs:
            None: Asserts no subsequent sample or healthy closure marker is produced.
        """
        def fatal(sample_id):
            """Reject a synthetic scope before performing any collection.

            Inputs:
                sample_id: Scheduled identifier retained only in fixture call history.
            Outputs:
                None: Raises CollectorAbort immediately.
            """
            self.calls.append((sample_id, self.now))
            raise CollectorAbort("synthetic fatal scope failure")
        with self.assertRaises(CollectorAbort):
            self.runner(collect=fatal).run()
        self.assertEqual(len(self.calls), 1)
        self.assertFalse(any(event["kind"] == "run_closed" for event in self.journal))

    def test_clock_jump_stall_and_extra_outputs_abort(self):
        """Fail closed on diverging clocks, a stalled scheduler or unexpected collector payloads.

        Inputs:
            Separate synthetic clock/sleeper and collector-contract failures.
        Outputs:
            None: Asserts no healthy completion marker for any failed run.
        """
        def jumping(sample_id):
            """Simulate a wall-clock step independent of elapsed monotonic time.

            Inputs:
                sample_id: Scheduled collector identifier.
            Outputs:
                dict: Fake source result while changing the simulated clock drift.
            """
            self.drift += 10
            return self.collect(sample_id)
        with self.assertRaises(ValueError):
            self.runner(collect=jumping).run()
        self.assertFalse(any(event["kind"] == "run_closed" for event in self.journal))
        self.setUp()
        def stalled(seconds):
            """Simulate a sleeper that fails to advance monotonic time.

            Inputs:
                seconds: Requested wait, deliberately ignored by this fault fixture.
            Outputs:
                None: Leaves the virtual clock unchanged; makes no real sleep.
            """
            return None
        with self.assertRaises(ValueError):
            self.runner(sleeper=stalled).run()
        self.assertFalse(any(event["kind"] == "run_closed" for event in self.journal))
        self.setUp()
        def unexpected(sample_id):
            """Return a forbidden synthetic score instead of capture metadata.

            Inputs:
                sample_id: Scheduled identifier, unused by this invalid contract fixture.
            Outputs:
                dict: Forbidden score field used only to prove response rejection.
            """
            return {"score": 0.99}
        with self.assertRaises(ValueError):
            self.runner(collect=unexpected).run()
        self.assertFalse(any(event["kind"] == "run_closed" for event in self.journal))

    def test_wrong_plan_pin_formal_phase_and_mutation_are_rejected(self):
        """Reject altered or formal plans before collector/journal callbacks execute.

        Inputs:
            Wrong trusted fingerprint, formal phase and internally changed plan variants.
        Outputs:
            None: Asserts validation failures with no source collection.
        """
        with self.assertRaises(ValueError):
            DevelopmentSamplingRunner(self.plan, "0"*64, self.collect, self.persist, self.wall, self.mono, self.sleep)
        self.plan["phase"] = "confirmatory"
        with self.assertRaises(ValueError):
            self.runner()
        self.setUp()
        runner = self.runner()
        runner.plan["run_id"] = "tampered"
        with self.assertRaises(ValueError):
            runner.run()
        self.assertEqual(self.calls, [])
        self.assertEqual(self.journal, [])

    def test_plan_scope_and_runtime_bounds_are_explicit(self):
        """Reject unsupported grace/skew/scope settings and excessively early launch.

        Inputs:
            Independent malformed plan edits and a virtual launch more than 1,800 seconds early.
        Outputs:
            None: Asserts no collector or journal callback before a valid bounded run starts.
        """
        original = copy.deepcopy(self.plan)
        for key, value in [("max_clock_skew_seconds", 61), ("collector_scope_sha256", "bad"),
                           ("expected", "compliant")]:
            self.plan = {**original, key: value}
            with self.assertRaises(ValueError):
                self.runner()
        self.plan = copy.deepcopy(original)
        self.plan["sampling"]["closed_at"] = self.stamp(3601)
        with self.assertRaises(ValueError):
            self.runner()
        self.plan = original
        self.now = -2000
        with self.assertRaises(ValueError):
            self.runner().run()
        self.assertEqual(self.calls, [])
        self.assertEqual(self.journal, [])
