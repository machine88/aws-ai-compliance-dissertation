"""Offline development acquisition audit; never invents state clocks or ML readiness."""
from datetime import timedelta
from research.catalog import canonical_sha256
from research.contracts import WINDOW_SECONDS
from research.timing import require_sha256, utc_timestamp
from research.trials import safe_id

VERSION = "development-sampling-audit-v0.1"
PLAN_KEYS = {"phase", "trigger_at", "closed_at", "max_start_lateness_seconds",
             "max_response_seconds", "max_anchor_age_seconds", "samples"}
RECEIPT_KEYS = {"sample_id", "request_started_at", "recorded_at", "source_observed_at",
                "status", "evidence_sha256"}


def nonnegative_seconds(value):
    """Require an explicit finite nonnegative integer timing bound.

    Inputs:
        value: Proposed timing bound in whole seconds; booleans are forbidden.
    Outputs:
        int: Unchanged bound; invalid values raise ValueError without side effects.
    """
    if type(value) is not int or value < 0 or value > WINDOW_SECONDS:
        raise ValueError("timing bounds must be integers between zero and the study horizon")
    return value


def audit_sampling(plan, receipts):
    """Audit acquisition timing without changing the existing feature or detection contract.

    Inputs:
        plan: Exact development plan with explicit timing bounds and one pre-trigger anchor.
        receipts: List of source-bound request receipts, at most one per scheduled sample.
    Outputs:
        dict: Plan hash, retained clocks, missing/error/late blockers and acquisition status.
            Never declares telemetry complete, produces features or admits formal trials.
            Malformed schemas/clocks raise ValueError; performs no IO or AWS calls.
    """
    if not isinstance(plan, dict) or set(plan) != PLAN_KEYS or plan["phase"] != "development":
        raise ValueError("exact development sampling plan required")
    start = utc_timestamp(plan["trigger_at"])
    cutoff = start + timedelta(seconds=WINDOW_SECONDS)
    closure = utc_timestamp(plan["closed_at"])
    if closure < cutoff:
        raise ValueError("administrative closure must not precede the shared horizon")
    lateness = nonnegative_seconds(plan["max_start_lateness_seconds"])
    response_limit = nonnegative_seconds(plan["max_response_seconds"])
    anchor_age = nonnegative_seconds(plan["max_anchor_age_seconds"])
    samples = plan["samples"]
    if not isinstance(samples, list) or not 2 <= len(samples) <= 1000:
        raise ValueError("bounded anchor and in-window schedule required")
    scheduled = {}
    offsets = []
    for item in samples:
        if not isinstance(item, dict) or set(item) != {"sample_id", "offset_seconds"}:
            raise ValueError("exact scheduled sample schema required")
        identifier = safe_id(item["sample_id"])
        offset = item["offset_seconds"]
        if type(offset) is not int or not -WINDOW_SECONDS <= offset <= WINDOW_SECONDS:
            raise ValueError("sample offset outside bounded development schedule")
        if identifier in scheduled:
            raise ValueError("duplicate scheduled identifier")
        scheduled[identifier] = offset
        offsets.append(offset)
    # A pre-trigger anchor is distinct from observations acquired during the window.
    if offsets != sorted(set(offsets)) or sum(offset < 0 for offset in offsets) != 1:
        raise ValueError("require ordered unique offsets and exactly one pre-trigger anchor")
    if not isinstance(receipts, list) or len(receipts) > len(samples):
        raise ValueError("bounded receipt list required")
    received = {}
    for receipt in receipts:
        if not isinstance(receipt, dict) or set(receipt) != RECEIPT_KEYS:
            raise ValueError("exact receipt schema required; labels/facts are not accepted")
        identifier = safe_id(receipt["sample_id"])
        if identifier not in scheduled or identifier in received:
            raise ValueError("unscheduled or duplicate receipt")
        if receipt["status"] not in ("success", "error"):
            raise ValueError("explicit request status required")
        require_sha256(receipt["evidence_sha256"])
        requested = utc_timestamp(receipt["request_started_at"])
        recorded = utc_timestamp(receipt["recorded_at"])
        source = None if receipt["source_observed_at"] is None else utc_timestamp(receipt["source_observed_at"])
        if requested > recorded or recorded > closure or (source is not None and source > recorded):
            raise ValueError("inverted or post-closure receipt clocks")
        received[identifier] = (receipt, requested, recorded, source)
    rows = []
    blockers = []
    for identifier, offset in scheduled.items():
        target = start + timedelta(seconds=offset)
        reasons = []
        row = {"sample_id": identifier, "role": "anchor" if offset < 0 else "window",
               "scheduled_at": target.isoformat(), "receipt": None}
        if identifier not in received:
            reasons.append("missing_receipt")
        else:
            receipt, requested, recorded, source = received[identifier]
            row["receipt"] = dict(receipt)
            delay = (requested - target).total_seconds()
            row.update(start_lateness_seconds=delay,
                       response_seconds=(recorded - requested).total_seconds(),
                       source_age_at_receipt_seconds=None if source is None else (recorded-source).total_seconds())
            if receipt["status"] == "error":
                reasons.append("request_error")
            if delay < 0:
                reasons.append("request_before_target")
            elif delay > lateness:
                reasons.append("late_request_start")
            if (recorded-requested).total_seconds() > response_limit:
                reasons.append("slow_response")
            if offset < 0:
                if recorded > start:
                    reasons.append("anchor_received_after_trigger")
                elif (start-recorded).total_seconds() > anchor_age:
                    reasons.append("anchor_too_old")
            elif recorded > cutoff:
                reasons.append("received_after_horizon")
        row["blockers"] = reasons
        blockers.extend({"sample_id": identifier, "reason": reason} for reason in reasons)
        rows.append(row)
    # Acquisition timing cannot substantiate source freshness, delivery or compliance.
    return {"version": VERSION, "phase": "development", "plan_sha256": canonical_sha256(plan),
            "cutoff_at": cutoff.isoformat(), "closed_at": closure.isoformat(),
            "samples": rows, "blockers": blockers, "acquisition_schedule_met": not blockers,
            "source_freshness_verified": False, "provider_delivery_verified": False,
            "ml_ready": False, "formal_trial_authorized": False}
