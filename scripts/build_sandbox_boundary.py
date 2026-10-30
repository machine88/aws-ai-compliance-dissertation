"""Reproduce the dedicated sandbox ceiling from generated actions and the reviewed S3 ceiling."""
import json
from pathlib import Path


def build_policies(root):
    """Constrain the generated candidate to one bucket and its isolated state keys.

    Inputs:
        root: Repository root containing unchanged baseline ceilings and raw Autopilot output.
    Outputs:
        tuple: Boundary and backend/read policy dictionaries; no IO writes or AWS operations.
            Rejects missing generated input and an oversized boundary rather than widening scope.
    """
    baseline = json.loads((root / "infra/access/deployment-boundary.json").read_text())
    generated = json.loads((root / "infra/access/generated-sandbox-policy.json").read_text())
    prior_reads = json.loads((root / "infra/access/backend-and-read-policy.json").read_text())
    bucket = "arn:aws:s3:::dissertation-sandbox-653464153304-us-east-2-s3-01"
    state = "arn:aws:s3:::dissertation-653464153304-us-east-2-state"
    key = "dissertation/653464153304/us-east-2/development-sandbox/terraform.tfstate"
    region = {"StringEquals": {"aws:RequestedRegion": "us-east-2"}}
    generated_actions = {a for s in generated["Statement"] for a in s["Action"]}
    ceiling = next(s["Action"] for s in baseline["Statement"] if s["Sid"] == "B03")
    # Preserve only reviewed bucket actions that the generated candidate actually requests.
    bucket_actions = sorted(generated_actions.intersection(ceiling))
    assert "s3:CreateBucket" in bucket_actions and "s3:PutBucketPolicy" in bucket_actions
    metadata_actions = next(s["Action"] for s in prior_reads["Statement"] if s["Sid"] == "B03")
    # Backend operations are copied from the existing reviewed pattern, with exact new keys.
    backend = {"Version": "2012-10-17", "Statement": []}
    for original in prior_reads["Statement"]:
        if original["Sid"] in {"B03", "B04", "B05", "B06", "B07"}:
            statement = json.loads(json.dumps(original).replace("/baseline/", "/development-sandbox/"))
            if statement["Sid"] == "B03":
                statement["Resource"] = [bucket]
            backend["Statement"].append(statement)
    actions = sorted(set(bucket_actions + metadata_actions + ["s3:GetObject", "s3:PutObject", "s3:DeleteObject", "sts:GetCallerIdentity"]))
    boundary = {"Version": "2012-10-17", "Statement": [
        {"Sid": "DenyOtherActions", "Effect": "Deny", "NotAction": actions, "Resource": "*"},
        {"Sid": "DenyOtherStorage", "Effect": "Deny", "Action": "s3:*", "NotResource": [bucket, state, f"{state}/{key}", f"{state}/{key}.tflock"]},
        {"Sid": "Identity", "Effect": "Allow", "Action": ["sts:GetCallerIdentity"], "Resource": "*"},
        {"Sid": "SandboxConfiguration", "Effect": "Allow", "Action": bucket_actions, "Resource": [bucket], "Condition": region},
        *backend["Statement"],
    ]}
    # A single managed boundary must fit IAM's policy quota before being proposed.
    if len(json.dumps(boundary, separators=(",", ":"))) > 6144:
        raise ValueError("Dedicated sandbox boundary exceeds the managed-policy limit")
    return boundary, backend


def main():
    """Write reproducible candidate policies for review, without contacting AWS.

    Inputs:
        None: Uses this checkout's reviewed policy inputs.
    Outputs:
        None: Writes two candidate policy files and prints size; never grants live permissions.
    """
    root = Path(__file__).resolve().parents[1]
    boundary, backend = build_policies(root)
    for name, payload in [("sandbox-boundary.json", boundary), ("sandbox-state-and-read-policy.json", backend)]:
        (root / "infra/access" / name).write_text(json.dumps(payload, indent=2) + "\n")
    print(f"Candidate boundary: {len(json.dumps(boundary, separators=(',', ':')))} characters; no AWS changes.")


if __name__ == "__main__":
    main()
