"""Development-only S3 event features with explicit scope, receipt cutoff and completeness gates."""
from research.aws_reader import ACCOUNT, REGION, BUCKETS
from research.catalog import canonical_sha256
from research.contracts import FACTS, WINDOW_SECONDS
from research.timing import require_sha256, utc_timestamp

EXTRACTION_VERSION = "development-s3-event-features-v0.1"
# Inputs: explicit bucket-configuration mutation names. Output: eligible feature categories.
MUTATIONS = {
    "PutBucketPolicy": "policy_change_count", "DeleteBucketPolicy": "policy_change_count",
    "PutBucketPublicAccessBlock": "public_access_change_count",
    "DeleteBucketPublicAccessBlock": "public_access_change_count",
    "PutBucketVersioning": "versioning_change_count",
}
STATE_FACTS = {name.split(".", 1)[1] for name in FACTS}
COVERAGE_KEYS = {"phase", "account_id", "region", "bucket", "window_start", "window_end", "closed_at",
                 "pages_complete", "delivery_verified", "snapshots_complete", "source_manifest_sha256"}


def extract_event_features(envelopes, snapshots, coverage):
    """Derive proposed numeric features only from scoped, available and declared complete inputs.

    Inputs:
        envelopes: Decoded event/collector_recorded_at pairs; original events are never model columns.
        snapshots: Timestamped full unprefixed technical-fact dictionaries at scheduled observation points.
        coverage: Exact development collection declaration, interval, source hash and completeness flags.
    Outputs:
        dict: Version, source hash, audit counts, blockers and numeric features only when ready.
            No AWS calls, file writes, model fit, truth join or proof of provider completeness.
    """
    if not isinstance(coverage, dict) or set(coverage) != COVERAGE_KEYS or coverage["phase"] != "development":
        raise ValueError("Exact development coverage declaration required")
    if coverage["account_id"] != ACCOUNT or coverage["region"] != REGION or coverage["bucket"] not in BUCKETS:
        raise ValueError("Coverage outside reviewed account, region or buckets")
    if not isinstance(envelopes, list) or not isinstance(snapshots, list):
        raise ValueError("Event and snapshot lists required")
    require_sha256(coverage["source_manifest_sha256"])
    start, end, closed = [utc_timestamp(coverage[key]) for key in ("window_start", "window_end", "closed_at")]
    if (end - start).total_seconds() != WINDOW_SECONDS or closed < end:
        raise ValueError("Closed 1800-second window required")
    blockers = []
    for key in ("pages_complete", "delivery_verified", "snapshots_complete"):
        if type(coverage[key]) is not bool:
            raise ValueError("Explicit boolean completeness declarations required")
        if not coverage[key]:
            blockers.append(key + "_false")
    features = {"mutation_count": 0, "policy_change_count": 0, "public_access_change_count": 0,
                "versioning_change_count": 0, "principal_count": 0, "configuration_delta_count": 0,
                "failed_request_fraction": 0.0}
    principals, seen, ignored = set(), {}, {}
    attempts, failures = 0, 0
    for envelope in envelopes:
        if not isinstance(envelope, dict) or set(envelope) != {"event", "collector_recorded_at"} or not isinstance(envelope["event"], dict):
            raise ValueError("Exact event envelope required")
        event = envelope["event"]
        name = event.get("eventName")
        # Monitoring reads, object/data events and other services are outside this feature definition.
        reason = None
        if event.get("eventSource") != "s3.amazonaws.com" or name not in MUTATIONS:
            reason = "operation_not_in_feature_allowlist"
        elif event.get("recipientAccountId") != ACCOUNT or event.get("awsRegion") != REGION:
            reason = "other_account_or_region"
        else:
            parameters = event.get("requestParameters")
            if not isinstance(parameters, dict) or not isinstance(parameters.get("bucketName"), str):
                blockers.append("unattributable_bucket_event")
                reason = "missing_bucket_identity"
            elif parameters["bucketName"] != coverage["bucket"]:
                reason = "other_bucket"
        if reason:
            ignored[reason] = ignored.get(reason, 0) + 1
            continue
        identifier = event.get("eventID")
        if not isinstance(identifier, str) or not identifier:
            blockers.append("missing_event_id")
            continue
        # Deduplicate original provider events, allowing repeated delivery at a later receipt time.
        provider_hash = canonical_sha256(event)
        if identifier in seen:
            if seen[identifier][0] != provider_hash:
                raise ValueError("Conflicting provider event IDs")
            seen[identifier][1].append(envelope)
        else:
            seen[identifier] = [provider_hash, [envelope]]
    for _, duplicates in seen.values():
        event = duplicates[0]["event"]
        occurred = utc_timestamp(event["eventTime"])
        receipts = [utc_timestamp(item["collector_recorded_at"]) for item in duplicates]
        received = min(receipts)
        if any(receipt < occurred or receipt > closed for receipt in receipts):
            raise ValueError("Invalid event/receipt ordering or receipt after declared closure")
        if not start <= occurred <= end:
            ignored["outside_source_window"] = ignored.get("outside_source_window", 0) + 1
            continue
        if received > end:
            # Do not use later delivery to improve a feature vector retrospectively.
            blockers.append("in_window_event_arrived_after_cutoff")
            continue
        if event.get("managementEvent") is not True or event.get("eventCategory") != "Management" or event.get("readOnly") is not False or event.get("eventType") != "AwsApiCall":
            blockers.append("unverified_management_mutation")
            continue
        identity = event.get("userIdentity", {})
        principal = identity.get("principalId") if isinstance(identity, dict) else None
        if not isinstance(principal, str) or not principal:
            blockers.append("missing_principal_id")
            continue
        principals.add(principal)
        attempts += 1
        failed = "errorCode" in event
        if failed and (not isinstance(event["errorCode"], str) or not event["errorCode"]):
            raise ValueError("Malformed error code")
        response = event.get("responseElements")
        if isinstance(response, dict) and any(key in response for key in ("errorCode", "errorMessage", "Error")):
            blockers.append("unsupported_nested_error_semantics")
            continue
        if "errorMessage" in event and not failed:
            blockers.append("error_message_without_code")
            continue
        if failed:
            failures += 1
        else:
            features["mutation_count"] += 1
            features[MUTATIONS[event["eventName"]]] += 1
    features["principal_count"] = len(principals)
    features["failed_request_fraction"] = failures / attempts if attempts else 0.0
    delta, snapshot_blockers = snapshot_delta_count(snapshots, start, end)
    features["configuration_delta_count"] = delta
    blockers.extend(snapshot_blockers)
    # An incomplete batch emits no numeric vector, preventing zero-imputation downstream.
    return {"extraction_version": EXTRACTION_VERSION, "phase": "development", "ml_ready": not blockers,
            "features": features if not blockers else None, "blockers": sorted(set(blockers)),
            "eligible_attempts": attempts, "failed_attempts": failures, "ignored_counts": ignored,
            "input_sha256": canonical_sha256({"events": envelopes, "snapshots": snapshots, "coverage": coverage}),
            "source_manifest_sha256": coverage["source_manifest_sha256"], "coverage_is_declaration_not_attestation": True,
            "independent_ground_truth_used": False}


def snapshot_delta_count(snapshots, start, end):
    """Count observed boolean attribute transitions without claiming continuous coverage.

    Inputs:
        snapshots: List of exact observed_at/collector_recorded_at/facts records with six booleans.
        start: UTC datetime marking the verified-by-caller interval start.
        end: UTC datetime marking the inclusive scoring cutoff.
    Outputs:
        tuple: Observed changed-attribute count and missing-coverage blockers; malformed inputs raise.
    """
    ordered = {}
    for snapshot in snapshots:
        if not isinstance(snapshot, dict) or set(snapshot) != {"observed_at", "collector_recorded_at", "facts"}:
            raise ValueError("Exact snapshot frame required")
        observed = utc_timestamp(snapshot["observed_at"])
        recorded = utc_timestamp(snapshot["collector_recorded_at"])
        if not start <= observed <= recorded <= end:
            raise ValueError("Snapshot outside available interval")
        facts = snapshot["facts"]
        if not isinstance(facts, dict) or set(facts) != STATE_FACTS or any(type(v) is not bool for v in facts.values()):
            return 0, ["incomplete_snapshot_facts"]
        if observed in ordered and ordered[observed] != facts:
            raise ValueError("Conflicting snapshots at the same source time")
        ordered[observed] = facts
    times = sorted(ordered)
    if not times or times[0] != start or times[-1] != end:
        return 0, ["missing_snapshot_endpoints"]
    changes = sum(ordered[a][name] != ordered[b][name] for a, b in zip(times, times[1:]) for name in STATE_FACTS)
    return changes, []
