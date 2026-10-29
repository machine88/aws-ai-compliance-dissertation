"""Bind development sampling receipts to verified encrypted snapshot records, never labels."""
from research.archive_ingestion import verify_archive
from research.aws_reader import read_plan
from research.catalog import canonical_sha256
from research.sampling import audit_sampling
from research.timing import require_sha256


def audit_snapshot_sampling(plan, sources, decrypt_record, recipient_sha256, bucket, request_sha256):
    """Verify pinned archives before projecting one reviewed operation into sampling receipts.

    Inputs:
        plan: Exact development sampling plan accepted by audit_sampling.
        sources: List of sample_id/root/archive_sha256/record_sha256 bindings chosen independently.
        decrypt_record: Trusted authenticated decryption callback passed to verify_archive.
        recipient_sha256: Independently trusted normalized public certificate fingerprint.
        bucket: Independently reviewed research bucket used to verify every snapshot scope.
        request_sha256: Hash of one non-paginated maintained request shared by all samples.
    Outputs:
        dict: Sampling audit, hash-only source bindings and explicit legacy-timing blockers.
            No raw responses, archive paths, facts, labels or decrypted files are emitted.
            Malformed or mismatched sources fail; does no AWS call, training or capture.
    """
    # Validate the plan before reading/decrypting any source; missing receipts are allowed.
    audit_sampling(plan, [])
    require_sha256(recipient_sha256)
    require_sha256(request_sha256)
    allowed = {canonical_sha256(request) for request in read_plan(bucket) if not request["paginated"]}
    if request_sha256 not in allowed:
        raise ValueError("One maintained non-paginated request must be selected independently")
    if not isinstance(sources, list) or len(sources) > len(plan["samples"]):
        raise ValueError("Bounded explicit snapshot bindings required")
    sample_ids = {item["sample_id"] for item in plan["samples"]}
    used_samples, used_records = set(), set()
    receipts, bindings, timing_blockers = [], [], []
    for source in sources:
        if not isinstance(source, dict) or set(source) != {"sample_id", "root", "archive_sha256", "record_sha256"}:
            raise ValueError("Exact source binding required; labels and clock overrides are forbidden")
        identifier = source["sample_id"]
        if not isinstance(identifier, str) or identifier not in sample_ids or identifier in used_samples:
            raise ValueError("Unscheduled or duplicate sample binding")
        used_samples.add(identifier)
        require_sha256(source["archive_sha256"])
        require_sha256(source["record_sha256"])
        if source["record_sha256"] in used_records:
            raise ValueError("A captured record cannot stand in for multiple scheduled samples")
        used_records.add(source["record_sha256"])
        verified = verify_archive(source["root"], decrypt_record, recipient_sha256, bucket)
        if verified["capture_kind"] != "snapshot" or verified["archive_sha256"] != source["archive_sha256"]:
            raise ValueError("Pinned snapshot archive differs from verified source")
        matches = [record for record in verified["records"] if canonical_sha256(record) == source["record_sha256"]]
        if len(matches) != 1:
            raise ValueError("Exactly one pinned source record required")
        record = matches[0]
        if record.get("kind") not in {"response", "absent"} or canonical_sha256(record.get("request")) != request_sha256:
            raise ValueError("Source record must match the independently selected request")
        bindings.append({"sample_id": identifier, "archive_sha256": source["archive_sha256"],
                         "record_sha256": source["record_sha256"], "request_sha256": request_sha256})
        if "request_started_at" not in record or "collector_recorded_at" not in record:
            timing_blockers.append({"sample_id": identifier, "reason": "capture_request_timing_unavailable"})
            continue
        # S3 configuration calls supply no comparable source observation clock here.
        # Explicit optional absence is a successful observation, not a compliance label.
        receipts.append({"sample_id": identifier, "request_started_at": record["request_started_at"],
                         "recorded_at": record["collector_recorded_at"], "source_observed_at": None,
                         "status": "success", "evidence_sha256": source["record_sha256"]})
    result = audit_sampling(plan, receipts)
    return {"version": "development-verified-sampling-v0.1", "phase": "development",
            "sampling": result, "source_bindings": bindings, "capture_timing_blockers": timing_blockers,
            "sender_authenticated": False, "provider_delivery_verified": False,
            "ml_ready": False, "formal_trial_authorized": False}
