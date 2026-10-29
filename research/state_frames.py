"""Offline six-fact S3 frames with per-request acquisition provenance, never atomic timestamps."""
from research.archive_ingestion import verify_archive
from research.aws_reader import read_plan
from research.catalog import canonical_sha256
from research.observations import PUBLIC_ACCESS
from research.sampling import nonnegative_seconds
from research.timing import require_sha256, utc_timestamp

# These three configuration reads supply six facts; absence never fills unknown flags.
FACT_OPERATIONS = {**{name: "get_public_access_block" for name in PUBLIC_ACCESS.values()},
                   "versioning_enabled": "get_bucket_versioning", "tls_deny_present": "get_bucket_policy"}


def build_state_frame(root, decrypt_record, recipient_sha256, bucket, archive_sha256,
                      record_pins, cutoff_at, max_acquisition_span_seconds):
    """Project a verified snapshot into facts with independently pinned request intervals.

    Inputs:
        root: Private encrypted snapshot directory passed to the existing archive verifier.
        decrypt_record: Trusted authenticated decryption callback; never logs plaintext or keys.
        recipient_sha256: Independently trusted normalized public certificate fingerprint.
        bucket: Independently reviewed research bucket used for scope verification.
        archive_sha256: Independently pinned complete archive fingerprint.
        record_pins: Exact operation-to-record-hash map for the three maintained fact reads.
        cutoff_at: Explicit timezone-aware receipt cutoff; not a claimed source observation time.
        max_acquisition_span_seconds: Explicit development span limit, integer zero through 1,800.
    Outputs:
        dict: Six boolean/unknown facts, per-fact source hashes/clocks, acquisition bounds and blockers.
            Writes no plaintext; makes no AWS call, features, labels or readiness claims.
            Invalid pins, scopes or clock ordering raise ValueError; legacy timing stays blocked.
    """
    require_sha256(archive_sha256)
    operations = set(FACT_OPERATIONS.values())
    if not isinstance(record_pins, dict) or set(record_pins) != operations:
        raise ValueError("Exactly three independently pinned fact operations required")
    for pin in record_pins.values():
        require_sha256(pin)
    cutoff = utc_timestamp(cutoff_at)
    limit = nonnegative_seconds(max_acquisition_span_seconds)
    verified = verify_archive(root, decrypt_record, recipient_sha256, bucket)
    if verified["capture_kind"] != "snapshot" or verified["archive_sha256"] != archive_sha256:
        raise ValueError("Verified snapshot differs from independently pinned archive")
    requests = {request["operation"]: canonical_sha256(request) for request in read_plan(bucket)
                if request["operation"] in operations}
    selected = {}
    ordered_intervals = []
    blockers = []
    for record in verified["records"]:
        operation = record.get("request", {}).get("operation")
        if operation not in operations:
            continue
        if operation in selected or record.get("kind") not in {"response", "absent"}:
            raise ValueError("Exactly one response or supported absence per fact operation required")
        if canonical_sha256(record) != record_pins[operation] or canonical_sha256(record["request"]) != requests[operation]:
            raise ValueError("Fact record differs from pinned record or maintained request")
        # Optional absence is still an observed API response, with facts derived by the adapter.
        start_value, end_value = record.get("request_started_at"), record.get("collector_recorded_at")
        start = utc_timestamp(start_value) if "request_started_at" in record else None
        end = utc_timestamp(end_value) if "collector_recorded_at" in record else None
        if start is None or end is None:
            blockers.append("missing_request_timing:" + operation)
        else:
            if start > end:
                raise ValueError("Request clocks are inverted")
            if ordered_intervals and start < ordered_intervals[-1][1]:
                raise ValueError("Serial snapshot acquisition intervals overlap or move backward")
            ordered_intervals.append((start, end))
        if end is not None and end > cutoff:
            blockers.append("received_after_cutoff:" + operation)
        selected[operation] = {"record_sha256": record_pins[operation], "request_sha256": requests[operation],
                               "request_started_at": start_value, "collector_recorded_at": end_value,
                               "source_observed_at": None}
    if set(selected) != operations:
        raise ValueError("Missing pinned fact record")
    facts, provenance = {}, {}
    observed = verified["normalized"]["observed_facts"]
    for fact, operation in FACT_OPERATIONS.items():
        facts[fact] = observed.get("end." + fact)
        provenance[fact] = dict(selected[operation])
        if facts[fact] is None:
            blockers.append("unknown_fact:" + fact)
    # The interval bounds describe acquisition, not simultaneous state or source freshness.
    span, earliest, latest = None, None, None
    if len(ordered_intervals) == len(operations):
        earliest = ordered_intervals[0][0]
        latest = ordered_intervals[-1][1]
        span = (latest-earliest).total_seconds()
        if span > limit:
            blockers.append("acquisition_span_exceeds_bound")
    return {"version": "development-per-fact-frame-v0.1", "phase": "development",
            "archive_sha256": archive_sha256,
            "binding_sha256": canonical_sha256({"recipient_sha256": recipient_sha256, "bucket": bucket,
                "archive_sha256": archive_sha256, "record_pins": record_pins,
                "cutoff_at": cutoff_at, "max_acquisition_span_seconds": limit}),
            "facts": facts, "fact_provenance": provenance,
            "acquisition_started_at": None if earliest is None else earliest.isoformat(),
            "acquisition_recorded_at": None if latest is None else latest.isoformat(),
            "acquisition_span_seconds": span, "cutoff_at": cutoff.isoformat(),
            "max_acquisition_span_seconds": limit, "all_facts_known": all(v is not None for v in facts.values()),
            "frame_checks_passed": not blockers, "blockers": sorted(blockers),
            "atomic_snapshot_established": False, "source_freshness_verified": False,
            "sender_authenticated": False, "provider_delivery_verified": False,
            "ml_ready": False, "formal_trial_authorized": False}
