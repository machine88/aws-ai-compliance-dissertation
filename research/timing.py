"""Offline development timing ledger with explicit censoring and source/recorded clocks."""
import copy
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from operator import itemgetter
from research.catalog import canonical_sha256
from research.contracts import PROPOSAL_SHA256, WINDOW_SECONDS
from research.trials import MONITORS, OUTCOMES, safe_id

# These semantics are proposed for review; no formal timing protocol is frozen yet.
TIMING_VERSION = "development-recorded-clock-v0.1"
CLOCK_POLICY = "collector_recorded_time"
WINDOW_KEYS = {"phase", "trial_id", "scenario_id", "resource_id", "target", "catalog_version",
               "trigger_at", "trigger_verified", "trigger_evidence_sha256", "closed_at",
               "collection_complete", "observation_window_seconds", "clock_policy", "context"}
EVENT_KEYS = {"event_id", "monitor", "trial_id", "scenario_id", "resource_id", "target", "outcome",
              "source_status", "source_observed_at", "detected_at", "recorded_at", "evidence_sha256", "failure_reason"}
CONTEXT_KEYS = {"catalog_sha256", "assignments_sha256", "ground_truth_sha256"}


def require_sha256(value):
    """Reject missing or malformed evidence identities before trusting timing records.

    Inputs:
        value: Expected lowercase hexadecimal SHA-256 string.

    Outputs:
        str: Validated hash; invalid values raise ValueError.
    """
    if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise ValueError("SHA-256 evidence identity required")
    return value


def utc_timestamp(value):
    """Parse an explicit timezone-aware timestamp and normalize equivalent clocks to UTC.

    Inputs:
        value: ISO-8601 datetime string containing a UTC offset or Z suffix.

    Outputs:
        datetime: Timezone-aware UTC value; naive or invalid timestamps raise ValueError.
    """
    if not isinstance(value, str):
        raise ValueError("timestamp must be an ISO-8601 string")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timestamps need an explicit timezone")
    return parsed.astimezone(timezone.utc)


def validate_window(window):
    """Validate one shared development horizon without declaring a technical failure valid.

    Inputs:
        window: Exact timing-window metadata with trigger evidence, closure, health and design hashes.

    Outputs:
        tuple: Validated copied metadata, UTC start, fixed end and declared ledger closure time.
    """
    if set(window) != WINDOW_KEYS or window["phase"] != "development":
        raise ValueError("exact development window schema required")
    for key in ("trial_id", "scenario_id", "resource_id"):
        safe_id(window[key])
    if not isinstance(window["target"], str) or not window["target"] or not isinstance(window["catalog_version"], str) or not window["catalog_version"]:
        raise ValueError("mapping target and catalog version required")
    if type(window["observation_window_seconds"]) is not int or window["observation_window_seconds"] != WINDOW_SECONDS or window["clock_policy"] != CLOCK_POLICY:
        raise ValueError("fixed 1800-second horizon and explicit proposed clock policy required")
    if type(window["trigger_verified"]) is not bool or type(window["collection_complete"]) is not bool:
        raise ValueError("explicit trigger and collection health declarations required")
    require_sha256(window["trigger_evidence_sha256"])
    if set(window["context"]) != CONTEXT_KEYS:
        raise ValueError("complete predeclared design context required")
    for value in window["context"].values():
        require_sha256(value)
    # A declaration can be retained even when it records an unverified trigger or incomplete collection.
    start, closed = utc_timestamp(window["trigger_at"]), utc_timestamp(window["closed_at"])
    return copy.deepcopy(window), start, start + timedelta(seconds=WINDOW_SECONDS), closed


def validate_event(event):
    """Check event schema, evidence identity and causal timestamp ordering.

    Inputs:
        event: One baseline/AI determination with source, detection and recorded timestamps.

    Outputs:
        tuple: UTC source-observation, detection and collector-recording times; malformed events raise ValueError.
    """
    if set(event) != EVENT_KEYS or event["monitor"] not in MONITORS or event["outcome"] not in OUTCOMES:
        raise ValueError("invalid timing-event schema, monitor or outcome")
    for key in ("event_id", "trial_id", "scenario_id", "resource_id"):
        safe_id(event[key])
    require_sha256(event["evidence_sha256"])
    if event["source_status"] is not None and not isinstance(event["source_status"], str):
        raise ValueError("source status must preserve a string or explicit null")
    if event["outcome"] == "instrument_failure":
        if not isinstance(event["failure_reason"], str) or not event["failure_reason"].strip():
            raise ValueError("instrumentation failure needs a documented reason and evidence")
    elif event["failure_reason"] is not None:
        raise ValueError("normal outcomes cannot carry an implicit exclusion reason")
    source, detected, recorded = [utc_timestamp(event[key]) for key in ("source_observed_at", "detected_at", "recorded_at")]
    # Clock inversions are technical failures, never negative or artificially fast latencies.
    if not source <= detected <= recorded:
        raise ValueError("source, detection and recorded clocks are out of order")
    return source, detected, recorded


def summarize_monitor(window, monitor, events):
    """Find the first attributable recorded noncompliance signal without reading labels.

    Inputs:
        window: Shared development trigger, horizon and predeclared design metadata.
        monitor: Baseline or ai source to summarize.
        events: Raw determination events from both monitoring approaches, retained for audit.

    Outputs:
        dict: Valid determinations, ignored-event reasons, technical failures and first noncompliance signal; no truth-dependent metric.
    """
    window, start, end, closed = validate_window(window)
    if monitor not in MONITORS:
        raise ValueError("unknown monitor")
    failures, ignored, determinations, signals = [], [], [], []
    if not window["trigger_verified"]:
        failures.append({"reason": "unverified_trigger"})
    if not window["collection_complete"]:
        failures.append({"reason": "incomplete_required_collection"})
    if closed < end:
        failures.append({"reason": "observation_window_not_closed"})
    seen = {}
    for event in events:
        if not isinstance(event, dict):
            failures.append({"reason": "malformed_event"})
            continue
        identifier = event.get("event_id")
        if event.get("monitor") not in MONITORS:
            failures.append({"event_id": identifier, "reason": "unknown_monitor_identity"})
            continue
        if event.get("monitor") != monitor:
            ignored.append({"event_id": identifier, "reason": "other_monitor"})
            continue
        # Unrelated resources/scenarios never become detections for the current trial.
        if any(key in event and event[key] != window[key] for key in ("trial_id", "scenario_id", "resource_id", "target")):
            ignored.append({"event_id": identifier, "reason": "different_trial_resource_or_target"})
            continue
        try:
            source, detected, recorded = validate_event(event)
            digest = canonical_sha256(event)
            if identifier in seen:
                if seen[identifier] != digest:
                    raise ValueError("event ID reused with conflicting contents")
                ignored.append({"event_id": identifier, "reason": "duplicate_event"})
                continue
            seen[identifier] = digest
            if recorded > closed:
                raise ValueError("event was recorded after declared ledger closure")
        except (ValueError, TypeError, KeyError) as error:
            failures.append({"event_id": identifier, "reason": "invalid_event_or_clock", "detail": str(error)})
            continue
        # Keep late arrivals and stale provider state in the audit, without backdating a valid detection.
        if recorded < start or source < start or detected < start:
            ignored.append({"event_id": identifier, "reason": "stale_or_pretrigger_evidence"})
            continue
        # A documented failure affecting this window can be discovered after the horizon.
        if event["outcome"] == "instrument_failure" and source <= end:
            failures.append({"event_id": identifier, "reason": "documented_instrument_failure", "detail": event["failure_reason"]})
            continue
        if recorded > end:
            ignored.append({"event_id": identifier, "reason": "recorded_after_observation_horizon"})
            continue
        # WARNING/NOT_AVAILABLE with normal unknown behavior are retained, not automatically invalidated.
        if event["outcome"] in {"compliant", "noncompliant"}:
            determinations.append({"event_id": identifier, "outcome": event["outcome"], "recorded_at": recorded.isoformat()})
        if event["outcome"] == "noncompliant":
            signals.append({"event_id": identifier, "recorded_at": recorded.isoformat(),
                            "detected_at": detected.isoformat(), "source_observed_at": source.isoformat(),
                            "elapsed_seconds": (recorded - start).total_seconds()})
    # Sorting gives stable first-detection selection even when input pages arrive out of order.
    signals.sort(key=itemgetter("recorded_at", "event_id"))
    determinations.sort(key=itemgetter("recorded_at", "event_id"))
    return {"monitor": monitor, "quality": "instrument_failure" if failures else "valid",
            "failures": failures, "ignored_events": ignored, "valid_determinations": determinations,
            "has_valid_determination": bool(determinations), "first_noncompliance": signals[0] if signals else None,
            "clock_policy": CLOCK_POLICY, "horizon_seconds": WINDOW_SECONDS}


def write_timing_ledger(destination, window, events):
    """Retain both monitors' shared window and derived timing summaries immutably.

    Inputs:
        destination: New private JSON ledger file.
        window: Shared development window and design/answer-key fingerprints.
        events: Observed events; they may include normal non-detections or documented failures.

    Outputs:
        Path: Mode-600 checksummed ledger containing raw inputs and both summaries.
    """
    # Labels never enter this stage; derive both summaries against one unchanged window.
    window, _, _, _ = validate_window(window)
    payload = {"timing_version": TIMING_VERSION, "window": window, "events": copy.deepcopy(events),
               "summaries": {monitor: summarize_monitor(window, monitor, events) for monitor in sorted(MONITORS)}}
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x") as stream:
        os.chmod(path, 0o600)
        json.dump({"payload": payload, "payload_sha256": canonical_sha256(payload)}, stream,
                  indent=2, sort_keys=True, allow_nan=False)
    return path


def evaluate_saved_timing(path, truth):
    """Derive paired censoring/FN records only after the raw timing ledger persists.

    Inputs:
        path: Existing checksummed development timing ledger.
        truth: Separate predeclared answer-key document matching the ledger fingerprint and catalog version.

    Outputs:
        dict: Paired truth-dependent timing records; invalid trials and compliant cases receive no primary latency/FN value.
    """
    envelope = json.loads(Path(path).read_text())
    payload = envelope["payload"]
    if envelope["payload_sha256"] != canonical_sha256(payload) or payload["timing_version"] != TIMING_VERSION:
        raise ValueError("timing ledger checksum or contract version mismatch")
    window, _, _, _ = validate_window(payload["window"])
    if canonical_sha256(truth) != window["context"]["ground_truth_sha256"] or truth["proposal_sha256"] != PROPOSAL_SHA256 or truth["catalog_version"] != window["catalog_version"]:
        raise ValueError("predeclared expected-answer source changed")
    expected = truth["entries"][window["scenario_id"]]["expected"]
    if expected not in {"compliant", "noncompliant"}:
        raise ValueError("invalid expected state")
    summaries = {monitor: summarize_monitor(window, monitor, payload["events"]) for monitor in sorted(MONITORS)}
    if summaries != payload["summaries"]:
        raise ValueError("stored timing summaries disagree with retained raw events")
    # A documented setup/collection failure makes the matched trial ineligible, not a model FN.
    pair_eligible = all(summary["quality"] == "valid" for summary in summaries.values())
    records = {}
    for monitor, summary in summaries.items():
        eligible = pair_eligible and expected == "noncompliant"
        detection = summary["first_noncompliance"]
        detected = bool(detection) if eligible else None
        records[monitor] = {"latency_eligible": eligible, "event_observed": detected,
                            "duration_seconds": (detection["elapsed_seconds"] if detection else WINDOW_SECONDS) if eligible else None,
                            "right_censored": not detected if eligible else None,
                            "false_negative": not detected if eligible else None,
                            "summary": summary}
    return {"timing_version": TIMING_VERSION, "expected": expected, "pair_eligible": pair_eligible,
            "trial_id": window["trial_id"], "context": window["context"], "monitors": records,
            "metric_policy": "accuracy/FPR fusion and unknown-compliant denominator remain unresolved"}
