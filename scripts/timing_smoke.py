"""Illustrate censoring flags with synthetic clocks, never measured monitor performance."""
import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from research.catalog import canonical_sha256
from research.contracts import PROPOSAL_SHA256
from research.timing import CLOCK_POLICY, evaluate_saved_timing, write_timing_ledger


def synthetic_stamp(seconds):
    """Generate a timezone-aware timestamp relative to one fixed synthetic trigger.

    Inputs:
        seconds: Offset from the arbitrary synthetic reference time.

    Outputs:
        str: UTC ISO-8601 timestamp; it is not an AWS observation.
    """
    return (datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=seconds)).isoformat()


def synthetic_event(identifier, monitor, recorded):
    """Create a fake determination whose source and detection precede recording.

    Inputs:
        identifier: Unique synthetic event identifier.
        monitor: Baseline or ai stream used in the illustration.
        recorded: Collector-recording offset from the fake trigger, in seconds.

    Outputs:
        dict: Attributable-looking test event with explicitly synthetic source status.
    """
    return {"event_id": identifier, "monitor": monitor, "trial_id": "SYNTHETIC-TIMING", "scenario_id": "SYNTHETIC-S001",
            "resource_id": "SYNTHETIC-R001", "target": "S3.5", "outcome": "noncompliant",
            "source_status": "SYNTHETIC-NO-AWS", "source_observed_at": synthetic_stamp(1798),
            "detected_at": synthetic_stamp(1799), "recorded_at": synthetic_stamp(recorded),
            "evidence_sha256": "d" * 64, "failure_reason": None}


def run_timing_smoke(destination):
    """Show that equal 1,800-second durations can represent different detection outcomes.

    Inputs:
        destination: New private ledger file; an existing ledger is never replaced.

    Outputs:
        dict: Synthetic-only event/censoring illustration with zero AWS calls or research trials.
    """
    truth = {"proposal_sha256": PROPOSAL_SHA256, "catalog_version": "synthetic-timing-only",
             "entries": {"SYNTHETIC-S001": {"expected": "noncompliant"}}}
    window = {"phase": "development", "trial_id": "SYNTHETIC-TIMING", "scenario_id": "SYNTHETIC-S001",
              "resource_id": "SYNTHETIC-R001", "target": "S3.5", "catalog_version": "synthetic-timing-only",
              "trigger_at": synthetic_stamp(0), "trigger_verified": True, "trigger_evidence_sha256": "a" * 64,
              "closed_at": synthetic_stamp(1860), "collection_complete": True, "observation_window_seconds": 1800,
              "clock_policy": CLOCK_POLICY, "context": {"catalog_sha256": "b" * 64, "assignments_sha256": "c" * 64,
                                                         "ground_truth_sha256": canonical_sha256(truth)}}
    # These clocks deliberately distinguish an endpoint detection from a late recorded arrival.
    events = [synthetic_event("SYNTHETIC-ENDPOINT", "baseline", 1800),
              synthetic_event("SYNTHETIC-LATE", "ai", 1801)]
    path = write_timing_ledger(destination, window, events)
    evaluation = evaluate_saved_timing(path, truth)
    return {"synthetic_only": True, "aws_calls": 0, "research_trials": 0,
            "illustration": {monitor: {key: record[key] for key in ("duration_seconds", "event_observed", "right_censored", "false_negative")}
                             for monitor, record in evaluation["monitors"].items()},
            "warning": "Illustrative clocks only; no model or AWS performance was measured."}


def main():
    """Write a fresh synthetic timing ledger and display its censoring illustration.

    Inputs:
        CLI --output naming a new private JSON ledger file.

    Outputs:
        None: Writes the raw checked ledger and prints explicitly synthetic timing outcomes.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    arguments = parser.parse_args()
    print(json.dumps(run_timing_smoke(arguments.output), indent=2))


# Importing the helpers has no execution effect; run the illustration only as a command.
if __name__ == "__main__":
    main()
