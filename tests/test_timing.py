"""Synthetic clock and censoring checks; these are not measured AWS results."""
import copy
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from research.catalog import canonical_sha256
from research.contracts import PROPOSAL_SHA256
from research.timing import (CLOCK_POLICY, evaluate_saved_timing, summarize_monitor,
                             utc_timestamp, validate_window, write_timing_ledger)


class TimingTests(unittest.TestCase):
    """Preserve valid non-detections and distinguish technical failures from model misses."""

    def setUp(self):
        """Prepare a fixed synthetic UTC window and independently retained answer source.

        Inputs:
            No external input; all timestamps and fingerprints are synthetic test fixtures.

        Outputs:
            None: Retains a 1,800-second window, closure after the horizon and a separate answer key.
        """
        self.start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        self.truth = {"proposal_sha256": PROPOSAL_SHA256, "catalog_version": "synthetic-timing-only",
                      "entries": {"S001": {"expected": "noncompliant"}}}
        self.window = {"phase": "development", "trial_id": "T001", "scenario_id": "S001", "resource_id": "R001",
                       "target": "S3.5", "catalog_version": "synthetic-timing-only", "trigger_at": self.stamp(0),
                       "trigger_verified": True, "trigger_evidence_sha256": "a" * 64, "closed_at": self.stamp(1860),
                       "collection_complete": True, "observation_window_seconds": 1800, "clock_policy": CLOCK_POLICY,
                       "context": {"catalog_sha256": "b" * 64, "assignments_sha256": "c" * 64,
                                   "ground_truth_sha256": canonical_sha256(self.truth)}}

    def stamp(self, seconds):
        """Convert an offset from the synthetic trigger into an explicit UTC timestamp.

        Inputs:
            seconds: Signed time offset used by a test case.

        Outputs:
            str: ISO-8601 timestamp including the UTC offset.
        """
        return (self.start + timedelta(seconds=seconds)).isoformat()

    def event(self, identifier="E001", monitor="baseline", seconds=60, outcome="noncompliant"):
        """Construct a causal attributable determination using placeholder evidence hashes.

        Inputs:
            identifier: Unique safe event ID within this synthetic monitor stream.
            monitor: Baseline or ai source.
            seconds: Collector-recording offset from the trigger.
            outcome: Explicit determination or unknown/instrumentation state.

        Outputs:
            dict: Complete synthetic event with source and detection times before recording.
        """
        return {"event_id": identifier, "monitor": monitor, "trial_id": "T001", "scenario_id": "S001",
                "resource_id": "R001", "target": "S3.5", "outcome": outcome, "source_status": None,
                "source_observed_at": self.stamp(seconds - 2), "detected_at": self.stamp(seconds - 1),
                "recorded_at": self.stamp(seconds), "evidence_sha256": "d" * 64,
                "failure_reason": "synthetic collector failure" if outcome == "instrument_failure" else None}

    def evaluated(self, events):
        """Persist the raw window before deriving truth-dependent timing outcomes.

        Inputs:
            events: Synthetic events to retain in a fresh temporary ledger.

        Outputs:
            dict: Paired latency evaluation; no lasting files or cloud operations.
        """
        with tempfile.TemporaryDirectory() as directory:
            path = write_timing_ledger(Path(directory) / "ledger.json", self.window, events)
            return evaluate_saved_timing(path, self.truth)

    def test_first_detection_is_order_independent_and_attributable(self):
        """Select the earliest valid signal instead of the latest event or unrelated resource.

        Inputs:
            Out-of-order repeated signals and a faster event for another resource.

        Outputs:
            None: Assertions require 30 seconds for baseline and preserve all valid determinations.
        """
        wrong = self.event("WRONG", seconds=3)
        wrong["resource_id"] = "R999"
        events = [self.event("LATER", seconds=80), wrong, self.event("FIRST", seconds=30), self.event("OK", seconds=20, outcome="compliant")]
        first = summarize_monitor(self.window, "baseline", events)
        second = summarize_monitor(self.window, "baseline", list(reversed(events)))
        self.assertEqual(first["first_noncompliance"], second["first_noncompliance"])
        self.assertEqual(first["first_noncompliance"]["elapsed_seconds"], 30)
        self.assertEqual(len(first["valid_determinations"]), 3)

    def test_endpoint_detection_and_censoring_have_different_event_flags(self):
        """Keep a real endpoint signal distinct from a non-detection at the same duration.

        Inputs:
            One baseline signal recorded at exactly 1,800 seconds; no AI determination.

        Outputs:
            None: Assertions require equal durations but different observed-event/censoring/FN flags.
        """
        report = self.evaluated([self.event(seconds=1800)])
        baseline, ai = report["monitors"]["baseline"], report["monitors"]["ai"]
        self.assertEqual((baseline["duration_seconds"], ai["duration_seconds"]), (1800, 1800))
        self.assertTrue(baseline["event_observed"])
        self.assertFalse(baseline["right_censored"])
        self.assertFalse(ai["event_observed"])
        self.assertTrue(ai["right_censored"])
        self.assertTrue(ai["false_negative"])

    def test_late_arrival_cannot_backdate_detection(self):
        """Use recorded time while retaining earlier provider/detection clocks for audit.

        Inputs:
            A baseline event observed/detected in-window but recorded one second late.

        Outputs:
            None: Assertions require a valid retained non-detection rather than an early credited detection.
        """
        event = self.event(seconds=1801)
        event["source_observed_at"] = self.stamp(20)
        event["detected_at"] = self.stamp(30)
        report = self.evaluated([event])
        baseline = report["monitors"]["baseline"]
        self.assertTrue(report["pair_eligible"])
        self.assertTrue(baseline["right_censored"])
        self.assertEqual(baseline["summary"]["ignored_events"][0]["reason"], "recorded_after_observation_horizon")

    def test_stale_evidence_does_not_establish_current_detection(self):
        """Reject a pre-trigger source observation even when its finding arrives later.

        Inputs:
            An otherwise valid event whose source observation predates the trigger.

        Outputs:
            None: Assertions require censoring with the stale-source reason retained.
        """
        event = self.event()
        event["source_observed_at"] = self.stamp(-1)
        report = self.evaluated([event])
        self.assertTrue(report["monitors"]["baseline"]["right_censored"])

    def test_unknown_warning_is_retained_without_automatic_invalidation(self):
        """Distinguish normal missing determinations from documented instrumentation failures.

        Inputs:
            An unknown result preserving the raw WARNING source status.

        Outputs:
            None: Assertions require a valid non-detection and no fabricated coverage.
        """
        event = self.event(outcome="unknown")
        event["source_status"] = "WARNING"
        report = self.evaluated([event])
        self.assertTrue(report["pair_eligible"])
        self.assertTrue(report["monitors"]["baseline"]["false_negative"])
        self.assertFalse(report["monitors"]["baseline"]["summary"]["has_valid_determination"])

    def test_documented_failure_invalidates_pair_without_creating_fn(self):
        """Retain a technical failure, including one discovered late, without counting it as a miss.

        Inputs:
            A documented baseline instrumentation failure and a valid AI signal.

        Outputs:
            None: Assertions require an ineligible pair and no fabricated primary latency/FN values.
        """
        failure = self.event(seconds=1801, outcome="instrument_failure")
        failure["source_observed_at"] = self.stamp(20)
        failure["detected_at"] = self.stamp(30)
        report = self.evaluated([failure, self.event("AI", "ai", 60)])
        self.assertFalse(report["pair_eligible"])
        for record in report["monitors"].values():
            self.assertIsNone(record["duration_seconds"])
            self.assertIsNone(record["false_negative"])

    def test_incomplete_or_unverified_window_cannot_be_censored_as_valid(self):
        """Avoid creating apparent model misses from unfinished or unverifiable trials.

        Inputs:
            Separate windows with incomplete collection, no verified trigger or premature closure.

        Outputs:
            None: Assertions require a technical-quality failure for each window.
        """
        for field, value in [("collection_complete", False), ("trigger_verified", False), ("closed_at", self.stamp(100))]:
            window = copy.deepcopy(self.window)
            window[field] = value
            self.assertEqual(summarize_monitor(window, "ai", [])["quality"], "instrument_failure")

    def test_clock_offsets_normalize_and_naive_timestamps_fail(self):
        """Normalize equivalent offset clocks while refusing missing timezone information.

        Inputs:
            Equivalent UTC/offset timestamps plus a naive time and an inverted event clock.

        Outputs:
            None: Assertions require normalized equality and explicit invalid-clock handling.
        """
        self.assertEqual(utc_timestamp("2026-01-01T01:00:00+01:00"), utc_timestamp("2026-01-01T00:00:00Z"))
        with self.assertRaises(ValueError):
            utc_timestamp("2026-01-01T00:00:00")
        event = self.event()
        event["detected_at"] = self.stamp(100)
        self.assertEqual(summarize_monitor(self.window, "baseline", [event])["quality"], "instrument_failure")

    def test_duplicate_ids_are_deduplicated_but_conflicts_are_failures(self):
        """Prevent repeated polling pages from inventing extra signals or hiding changed records.

        Inputs:
            An exact duplicate event, then a conflicting event using the same identifier.

        Outputs:
            None: Assertions require one signal for duplicates and invalid quality for conflicting contents.
        """
        event = self.event()
        summary = summarize_monitor(self.window, "baseline", [event, copy.deepcopy(event)])
        self.assertEqual(len(summary["valid_determinations"]), 1)
        conflicting = copy.deepcopy(event)
        conflicting["outcome"] = "compliant"
        self.assertEqual(summarize_monitor(self.window, "baseline", [event, conflicting])["quality"], "instrument_failure")

    def test_compliant_cases_have_no_primary_noncompliance_latency(self):
        """Keep compliant unknowns outside this latency endpoint without inventing an FPR rule.

        Inputs:
            A compliant answer key predeclared before a no-detection ledger is written.

        Outputs:
            None: Assertions require no primary latency or false-negative value for either monitor.
        """
        self.truth["entries"]["S001"]["expected"] = "compliant"
        self.window["context"]["ground_truth_sha256"] = canonical_sha256(self.truth)
        report = self.evaluated([])
        self.assertTrue(report["pair_eligible"])
        for record in report["monitors"].values():
            self.assertIsNone(record["duration_seconds"])
            self.assertIsNone(record["false_negative"])

    def test_ledger_and_answer_key_changes_are_rejected(self):
        """Require persisted original events and the predeclared separate expected answers.

        Inputs:
            A saved ledger followed by an altered answer key and an edited ledger payload.

        Outputs:
            None: Assertions require mismatch errors and no overwrite of retained evidence.
        """
        with tempfile.TemporaryDirectory() as directory:
            path = write_timing_ledger(Path(directory) / "ledger.json", self.window, [])
            changed = copy.deepcopy(self.truth)
            changed["entries"]["S001"]["expected"] = "compliant"
            with self.assertRaisesRegex(ValueError, "answer"):
                evaluate_saved_timing(path, changed)
            with self.assertRaises(FileExistsError):
                write_timing_ledger(path, self.window, [])
            envelope = json.loads(path.read_text())
            envelope["payload"]["window"]["trial_id"] = "changed"
            path.write_text(json.dumps(envelope))
            with self.assertRaisesRegex(ValueError, "checksum"):
                evaluate_saved_timing(path, self.truth)

    def test_shortened_horizon_and_formal_phase_are_refused(self):
        """Keep the proposal window fixed and refuse formal use of this development contract.

        Inputs:
            A shortened horizon followed by a confirmatory-phase declaration.

        Outputs:
            None: Assertions require both unsupported window definitions to fail.
        """
        self.window["observation_window_seconds"] = 60
        with self.assertRaises(ValueError):
            validate_window(self.window)
        self.window["observation_window_seconds"] = 1800
        self.window["phase"] = "confirmatory"
        with self.assertRaises(ValueError):
            validate_window(self.window)
