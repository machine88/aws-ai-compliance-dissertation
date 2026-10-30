"""Pure administrative checks for the deployed sandbox; no cloud access or research authorization."""
import json
from research.archive_ingestion import unique_object, reject_constant
from research.observations import tls_deny_recognized

VERSION = "sandbox-administrative-readiness-v0.1"
BUCKET = "dissertation-sandbox-653464153304-us-east-2-s3-01"
OPERATIONS = {"get_bucket_location", "get_bucket_tagging", "get_public_access_block",
              "get_bucket_ownership_controls", "get_bucket_versioning", "get_bucket_encryption",
              "get_bucket_policy", "get_bucket_policy_status", "list_objects_v2"}
TAGS = {"Project": "aws-ai-compliance-dissertation", "ManagedBy": "Terraform",
        "Phase": "development", "Purpose": "scenario-sandbox"}


def require_object(value, field):
    """Reject missing or malformed metadata containers without printing response contents.

    Inputs:
        value: Candidate JSON-style value for a required object.
        field: Fixed caller-supplied field description for a safe error message.
    Outputs:
        dict: Unmodified object; raises ValueError for any other type.
    """
    if not isinstance(value, dict):
        raise ValueError(f"Required metadata object: {field}")
    return value


def verify_sandbox_metadata(responses, bucket=BUCKET):
    """Check the specified deployment baseline and a complete empty current-object listing.

    Inputs:
        responses: Exact nine-operation mapping of caller-retained raw SDK response dictionaries.
        bucket: Fixed approved sandbox name; other targets are rejected rather than inferred.
    Outputs:
        dict: Administrative checks with scientific/ML/trigger gates false. Makes no IO or AWS
            calls, does not mutate input, authenticate sources, establish freshness, or authorize
            injection. Missing/malformed/changed protections or partial/nonempty listings raise.
    """
    if bucket != BUCKET or not isinstance(responses, dict) or set(responses) != OPERATIONS:
        raise ValueError("Exact sandbox scope and complete metadata operation set required")
    for name, value in responses.items():
        require_object(value, name)
    if responses["get_bucket_location"].get("LocationConstraint") != "us-east-2":
        raise ValueError("Sandbox location differs from the approved region")
    tags = responses["get_bucket_tagging"].get("TagSet")
    if not isinstance(tags, list) or len(tags) != len(TAGS):
        raise ValueError("Exact sandbox tags required")
    if any(not isinstance(tag, dict) or set(tag) != {"Key", "Value"} or not isinstance(tag["Key"], str) for tag in tags):
        raise ValueError("Malformed sandbox tags")
    if {tag["Key"]: tag["Value"] for tag in tags} != TAGS:
        raise ValueError("Sandbox tags differ from the deployment baseline")
    blocks = require_object(responses["get_public_access_block"].get("PublicAccessBlockConfiguration"), "public access")
    if not all(blocks.get(name) is True for name in ("BlockPublicAcls", "IgnorePublicAcls", "BlockPublicPolicy", "RestrictPublicBuckets")):
        raise ValueError("All four public-access protections must be explicitly true")
    ownership = require_object(responses["get_bucket_ownership_controls"].get("OwnershipControls"), "ownership")
    if ownership.get("Rules") != [{"ObjectOwnership": "BucketOwnerEnforced"}]:
        raise ValueError("Owner-enforced ACL-free ownership required")
    if responses["get_bucket_versioning"].get("Status") != "Enabled":
        raise ValueError("Versioning must match the Enabled deployment baseline")
    encryption = require_object(responses["get_bucket_encryption"].get("ServerSideEncryptionConfiguration"), "encryption")
    rules = encryption.get("Rules")
    if not isinstance(rules, list) or len(rules) != 1:
        raise ValueError("One explicit encryption rule required")
    rule = require_object(rules[0], "encryption rule")
    default = require_object(rule.get("ApplyServerSideEncryptionByDefault"), "default encryption")
    # AWS returns a container here, not the flat list used by Terraform's configuration field.
    blocked = require_object(rule.get("BlockedEncryptionTypes"), "blocked encryption types")
    if default.get("SSEAlgorithm") != "AES256" or blocked.get("EncryptionType") != ["SSE-C"] or rule.get("BucketKeyEnabled") is not False:
        raise ValueError("Explicit SSE-S3, SSE-C block and disabled bucket key required")
    raw_policy = responses["get_bucket_policy"].get("Policy")
    if not isinstance(raw_policy, str):
        raise ValueError("Retained policy JSON required")
    policy = json.loads(raw_policy, object_pairs_hook=unique_object, parse_constant=reject_constant)
    if not isinstance(policy, dict) or set(policy) != {"Version", "Statement"} or policy["Version"] != "2012-10-17":
        raise ValueError("Exact deployment policy envelope required")
    statements = policy["Statement"]
    if not isinstance(statements, list) or len(statements) != 1 or not tls_deny_recognized(policy, bucket):
        raise ValueError("A sole recognized TLS denial is required, with no access grants")
    statement = statements[0]
    resources = statement.get("Resource")
    if statement.get("Sid") != "RequireTLS" or statement.get("Action") not in ("s3:*", ["s3:*"]) or not isinstance(resources, list) or len(resources) != 2 or set(resources) != {f"arn:aws:s3:::{bucket}", f"arn:aws:s3:::{bucket}/*"}:
        raise ValueError("TLS denial must match the exact sandbox deployment scope")
    status = require_object(responses["get_bucket_policy_status"].get("PolicyStatus"), "policy status")
    if status.get("IsPublic") is not False:
        raise ValueError("Explicit nonpublic policy status required")
    listing = responses["list_objects_v2"]
    if listing.get("IsTruncated") is not False or type(listing.get("KeyCount")) is not int or listing["KeyCount"] != 0 or listing.get("Contents", []) != [] or listing.get("NextContinuationToken") is not None:
        raise ValueError("Complete empty current-object listing required")
    # This administrative predicate cannot prove owner identity, interval history or trial readiness.
    return {"version": VERSION, "bucket_protections_match_deployment": True,
            "complete_empty_current_listing": True, "source_identity_verified": False,
            "source_freshness_verified": False, "versions_delete_markers_multipart_empty_verified": False,
            "trigger_verified": False, "ml_ready": False, "formal_trial_authorized": False,
            "research_trials": 0}
