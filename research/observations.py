"""Pure development snapshot adapter: scoped facts and source statuses, never invented features."""
import json
from research.aws_reader import ACCOUNT, REGION, check_scope, read_plan, verify_identity
from research.catalog import canonical_sha256
from research.timing import utc_timestamp

ADAPTER_VERSION = "development-snapshot-observations-v0.1"
PUBLIC_ACCESS = {
    "BlockPublicAcls": "block_public_acls", "IgnorePublicAcls": "ignore_public_acls",
    "BlockPublicPolicy": "block_public_policy", "RestrictPublicBuckets": "restrict_public_buckets",
}
RULE_TARGETS = {"dissertation-research-public-access-blocks": "S3.8", "dissertation-research-tls-required": "S3.5"}


def tls_deny_recognized(policy, bucket):
    """Recognize only a conservative unconditional insecure-transport denial pattern.

    Inputs:
        policy: Decoded S3 bucket policy object, without expected scenario answers.
        bucket: Selected bucket whose ARN and object ARN must both be covered.
    Outputs:
        bool: True for a recognized sufficient deny; False means unrecognized, not compliant.
    """
    if not isinstance(policy, dict):
        raise ValueError("Policy must be a JSON object")
    statements = policy.get("Statement", [])
    if isinstance(statements, dict):
        statements = [statements]
    if not isinstance(statements, list) or any(not isinstance(s, dict) for s in statements):
        raise ValueError("Malformed policy statements")
    for statement in statements:
        # Extra conditions and Not* semantics need a real policy evaluator; never guess them.
        if set(statement) - {"Sid", "Effect", "Principal", "Action", "Resource", "Condition"}:
            continue
        action = statement.get("Action")
        action = [action] if isinstance(action, str) else action
        resources = statement.get("Resource")
        resources = [resources] if isinstance(resources, str) else resources
        condition = statement.get("Condition")
        if not isinstance(condition, dict) or set(condition) != {"Bool"}:
            continue
        boolean = condition["Bool"]
        if not isinstance(boolean, dict) or set(boolean) != {"aws:SecureTransport"}:
            continue
        insecure = boolean["aws:SecureTransport"] is False or boolean["aws:SecureTransport"] == "false"
        covered = isinstance(resources, list) and ("*" in resources or {f"arn:aws:s3:::{bucket}", f"arn:aws:s3:::{bucket}/*"}.issubset(set(resources)))
        if statement.get("Effect") == "Deny" and statement.get("Principal") in ("*", {"AWS": "*"}) and isinstance(action, list) and any(a in ("*", "s3:*") for a in action) and covered and insecure:
            return True
    return False


def normalize_snapshot(records, bucket, point="end"):
    """Project decoded collector records into label-free facts and separate source results.

    Inputs:
        records: In-memory decoded development envelopes from one trusted decryption boundary.
        bucket: One reviewed bucket; every request must match its maintained read plan exactly.
        point: Explicit start, middle or end observation slot; does not establish interval coverage.
    Outputs:
        dict: Hashed source references, partial facts, statuses and readiness limits. No AWS calls,
            file writes, ground-truth join, fused baseline decision or numeric ML feature values.
    """
    if point not in {"start", "middle", "end"} or not isinstance(records, list):
        raise ValueError("Explicit observation point and record list required")
    if not records or records[0].get("kind") != "identity" or records[-1].get("kind") != "completion":
        raise ValueError("Identity must precede observations and completion must close the snapshot")
    plan = read_plan(bucket)
    permitted = {canonical_sha256(request): request for request in plan}
    facts, statuses, unknown, seen, completions, identities = {}, [], [], {}, [], []
    available = set()
    for record in records:
        if not isinstance(record, dict) or record.get("kind") not in {"identity", "completion", "response", "absent", "instrumentation_error", "truncated"}:
            raise ValueError("Unknown collector envelope")
        kind = record["kind"]
        if kind in {"identity", "completion", "response"} and record.get("phase") != "development":
            raise ValueError("Development envelopes only")
        if kind == "identity":
            verify_identity(record["response"])
            identities.append(record)
            continue
        if kind == "completion":
            if type(record.get("complete")) is not bool:
                raise ValueError("Explicit completion declaration required")
            completions.append(record)
            continue
        request = record.get("request")
        request_hash = canonical_sha256(request)
        if request_hash not in permitted:
            raise ValueError("Request outside the reviewed snapshot plan")
        operation = request["operation"]
        digest = canonical_sha256(record)
        # Non-paginated responses cannot silently overwrite conflicting observations.
        if not request["paginated"]:
            if request_hash in seen and seen[request_hash] != digest:
                raise ValueError("Conflicting responses require separate snapshots")
            if request_hash in seen:
                continue
            seen[request_hash] = digest
        if kind != "response":
            unknown.append({"operation": operation, "kind": kind, "code": record.get("code"), "evidence_sha256": digest})
            if kind == "absent" and operation == "get_bucket_policy" and record.get("code") == "NoSuchBucketPolicy":
                facts[f"{point}.tls_deny_present"] = False
            continue
        utc_timestamp(record["collector_recorded_at"])
        response = record["response"]
        if not isinstance(response, dict):
            raise ValueError("AWS response must be an object")
        check_scope(operation, response)
        available.add(request_hash)
        if operation == "get_public_access_block":
            configuration = response.get("PublicAccessBlockConfiguration", {})
            for source, name in PUBLIC_ACCESS.items():
                if type(configuration.get(source)) is bool:
                    facts[f"{point}.{name}"] = configuration[source]
        elif operation == "get_bucket_versioning":
            status = response.get("Status")
            if status not in (None, "Enabled", "Suspended"):
                raise ValueError("Unexpected versioning status")
            facts[f"{point}.versioning_enabled"] = status == "Enabled"
        elif operation == "get_bucket_policy":
            policy = response.get("Policy")
            if not isinstance(policy, str):
                raise ValueError("Bucket policy must be serialized JSON")
            if tls_deny_recognized(json.loads(policy), bucket):
                facts[f"{point}.tls_deny_present"] = True
            else:
                unknown.append({"operation": operation, "kind": "policy_semantics_unresolved", "evidence_sha256": digest})
        elif operation in {"get_compliance_details_by_config_rule", "get_findings"}:
            statuses.extend(source_statuses(record, bucket))
    if len(identities) != 1 or len(completions) != 1:
        raise ValueError("Exactly one reader identity and completion declaration required")
    guards = [canonical_sha256(request) for request in plan[:2]]
    if any(key not in available for key in guards):
        raise ValueError("Successful location and project scope guards required")
    missing = [request["operation"] for key, request in permitted.items() if key not in available]
    return {"adapter_version": ADAPTER_VERSION, "phase": "development", "observation_point": point,
            "input_sha256": canonical_sha256(records), "observed_facts": facts, "source_statuses": statuses,
            "unknown_observations": unknown, "missing_response_operations": missing,
            "capture_declared_complete": completions[0]["complete"], "baseline_fusion": "unresolved",
            "ml_ready": False, "feature_blocker": "event_history_and_completeness_contract_not_available",
            "interval_coverage_established": False, "freshness_assessed": False}


def source_statuses(record, bucket):
    """Retain attributable Config/CSPM statuses without turning them into a fused prediction.

    Inputs:
        record: Successful response envelope for one reviewed Config rule or CSPM findings page.
        bucket: Exact selected bucket used to recheck returned resource identities.
    Outputs:
        list[dict]: Scoped source statuses, original clocks and envelope hash; no freshness claim.
    """
    request, response = record["request"], record["response"]
    digest = canonical_sha256(record)
    results = []
    if request["operation"] == "get_compliance_details_by_config_rule":
        target = RULE_TARGETS[request["params"]["ConfigRuleName"]]
        for item in response.get("EvaluationResults", []):
            identifier = item.get("EvaluationResultIdentifier", {})
            qualifier = identifier.get("EvaluationResultQualifier", {})
            if qualifier.get("ResourceType") != "AWS::S3::Bucket" or qualifier.get("ResourceId") != bucket or qualifier.get("ConfigRuleName") != request["params"]["ConfigRuleName"]:
                continue
            results.append({"source": "config", "target": target, "status": item.get("ComplianceType"),
                            "source_observed_at": identifier.get("OrderingTimestamp"), "detected_at": item.get("ResultRecordedTime"),
                            "recorded_at": record["collector_recorded_at"], "evidence_sha256": digest})
    else:
        for item in response.get("Findings", []):
            control = item.get("Compliance", {}).get("SecurityControlId")
            selected = any(r.get("Id") == f"arn:aws:s3:::{bucket}" and r.get("Type") == "AwsS3Bucket" for r in item.get("Resources", []))
            if item.get("AwsAccountId") != ACCOUNT or item.get("Region") != REGION or item.get("ProductName") != "Security Hub" or item.get("RecordState") != "ACTIVE" or control not in {"S3.5", "S3.8"} or not selected:
                continue
            # UpdatedAt is preserved as provider update time, not asserted to be first detection.
            results.append({"source": "securityhub_cspm", "target": control, "status": item["Compliance"].get("Status"),
                            "source_observed_at": item.get("LastObservedAt"), "provider_updated_at": item.get("UpdatedAt"),
                            "recorded_at": record["collector_recorded_at"], "evidence_sha256": digest})
    return results
