"""Build the reviewed maximum permissions for the paused-baseline deployment role."""
import json
from pathlib import Path


def allow(sid, actions, resources, condition=None):
    """Describe one explicitly scoped allowance in the permissions boundary."""
    statement = {"Sid": sid, "Effect": "Allow", "Action": actions, "Resource": resources}
    if condition:
        statement["Condition"] = condition
    return statement


def build_boundary(account="653464153304", region="us-east-2"):
    """Limit generated permissions to baseline provisioning and its isolated state key."""
    telemetry = f"arn:aws:s3:::dissertation-research-{account}-{region}-logs"
    state = f"arn:aws:s3:::dissertation-{account}-{region}-state"
    key = f"dissertation/{account}/{region}/baseline/terraform.tfstate"
    config_role = f"arn:aws:iam::{account}:role/aws-service-role/config.amazonaws.com/AWSServiceRoleForConfig"
    hub_role = f"arn:aws:iam::{account}:role/aws-service-role/securityhub.amazonaws.com/AWSServiceRoleForSecurityHub"
    requested_region = {"StringEquals": {"aws:RequestedRegion": region}}
    config_recorder = f"arn:aws:config:{region}:{account}:configuration-recorder/dissertation-research/*"
    config_rules = f"arn:aws:config:{region}:{account}:config-rule/*"
    statements = [
        # Explicit denials also protect against resource policies granting extra access.
        {"Sid": "DenyOtherStorage", "Effect": "Deny", "Action": "s3:*", "NotResource": [telemetry, state, f"{state}/{key}", f"{state}/{key}.tflock"]},
        {"Sid": "DenyPrivilegeChanges", "Effect": "Deny", "Action": ["iam:PutRolePolicy", "iam:AttachRolePolicy", "iam:DetachRolePolicy", "iam:CreatePolicyVersion", "iam:SetDefaultPolicyVersion", "iam:DeleteRolePermissionsBoundary", "iam:PutRolePermissionsBoundary", "iam:UpdateAssumeRolePolicy", "iam:CreateAccessKey", "iam:CreateUser", "iam:CreateRole", "sts:AssumeRole"], "Resource": "*"},
        allow("ResearchBucketConfiguration", ["s3:CreateBucket", "s3:PutBucketTagging", "s3:PutBucketPublicAccessBlock", "s3:PutBucketOwnershipControls", "s3:PutBucketVersioning", "s3:PutEncryptionConfiguration", "s3:PutBucketPolicy", "s3:GetAccelerateConfiguration", "s3:GetBucketAcl", "s3:GetBucketCORS", "s3:GetBucketLocation", "s3:GetBucketLogging", "s3:GetBucketObjectLockConfiguration", "s3:GetBucketOwnershipControls", "s3:GetBucketPolicy", "s3:GetBucketPolicyStatus", "s3:GetBucketPublicAccessBlock", "s3:GetBucketRequestPayment", "s3:GetBucketTagging", "s3:GetBucketVersioning", "s3:GetBucketWebsite", "s3:GetEncryptionConfiguration", "s3:GetLifecycleConfiguration", "s3:GetReplicationConfiguration", "s3:ListBucket"], [telemetry], requested_region),
        allow("StateBucketMetadata", ["s3:GetBucketLocation"], [state]),
        allow("ListBaselineStateOnly", ["s3:ListBucket"], [state], {"StringLike": {"s3:prefix": [key, key + ".tflock", f"dissertation/{account}/{region}/baseline/workspaces/*"]}}),
        allow("BaselineStateAndLock", ["s3:GetObject", "s3:PutObject"], [f"{state}/{key}", f"{state}/{key}.tflock"]),
        allow("ReleaseBaselineLockOnly", ["s3:DeleteObject"], [f"{state}/{key}.tflock"]),
        allow("ConfigRecorder", ["config:DescribeConfigurationRecorders", "config:DescribeConfigurationRecorderStatus", "config:PutConfigurationRecorder", "config:StopConfigurationRecorder"], [config_recorder], requested_region),
        allow("ConfigRuleCreation", ["config:PutConfigRule"], [config_rules], {"StringEquals": {"aws:RequestedRegion": region, "aws:RequestTag/Project": "aws-ai-compliance-dissertation"}}),
        allow("ConfigResearchTags", ["config:ListTagsForResource", "config:TagResource"], [config_recorder, config_rules], requested_region),
        # These Config operations do not support resource-level IAM scoping.
        allow("RegionalConfigDelivery", ["config:DescribeConfigRules", "config:DescribeDeliveryChannels", "config:PutDeliveryChannel"], ["*"], requested_region),
        allow("ResearchTrail", ["cloudtrail:AddTags", "cloudtrail:CreateTrail", "cloudtrail:GetTrail", "cloudtrail:GetEventSelectors", "cloudtrail:GetInsightSelectors", "cloudtrail:GetTrailStatus", "cloudtrail:ListTags", "cloudtrail:PutEventSelectors", "cloudtrail:StopLogging"], [f"arn:aws:cloudtrail:{region}:{account}:trail/dissertation-research"], requested_region),
        allow("RegionalTrailDiscovery", ["cloudtrail:DescribeTrails"], ["*"], requested_region),
        allow("PausedCSPMAccount", ["securityhub:DescribeHub", "securityhub:EnableSecurityHub", "securityhub:UpdateSecurityHubConfiguration", "securityhub:ListTagsForResource", "securityhub:TagResource"], [f"arn:aws:securityhub:{region}:{account}:hub/default"], requested_region),
        allow("ResearchBudget", ["budgets:ModifyBudget", "budgets:ViewBudget", "budgets:ListTagsForResource", "budgets:TagResource"], [f"arn:aws:budgets::{account}:budget/dissertation-research-account-alerts"]),
        allow("CreateRequiredServiceRoles", ["iam:CreateServiceLinkedRole"], [config_role, hub_role], {"StringEquals": {"iam:AWSServiceName": ["config.amazonaws.com", "securityhub.amazonaws.com"]}}),
        allow("InspectAndTagServiceRoles", ["iam:GetRole", "iam:ListRoleTags", "iam:TagRole"], [config_role, hub_role]),
        allow("PassConfigRoleOnly", ["iam:PassRole"], [config_role], {"StringEquals": {"iam:PassedToService": "config.amazonaws.com"}}),
    ]
    # Compact identifiers keep the managed policy below the IAM character limit.
    for index, statement in enumerate(statements, 1):
        statement["Sid"] = f"B{index:02d}"
    return {"Version": "2012-10-17", "Statement": statements}


def main():
    """Write a reproducible boundary for review; this script never calls AWS."""
    root = Path(__file__).resolve().parents[1]
    path = root / "infra/access/deployment-boundary.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    policy = build_boundary()
    compact_size = len(json.dumps(policy, separators=(",", ":")))
    if compact_size > 6144:
        raise SystemExit(f"Boundary exceeds IAM managed-policy limit: {compact_size}")
    path.write_text(json.dumps(policy, indent=2) + "\n")
    print(f"Boundary written for review ({compact_size} characters); no AWS changes.")


if __name__ == "__main__":
    main()
