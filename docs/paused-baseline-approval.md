# Paused monitoring baseline: deployment approval pending

This is a real saved plan using the remote baseline state key and the existing bounded deployment role. Nothing in this plan has been applied. Bootstrap and access state migrations are already complete.

Plan SHA-256: `ec631cbaf57d03cc16d9fd12637d8e7b3a1afdd68b160466a953b54b8d5f84a5`.

Account: `653464153304`. Research region: `us-east-2`. Billing endpoint: `us-east-1`. The backend and both providers assume `dissertation-paused-baseline-deploy`; the identity guard rejects ordinary IAM-user sessions as well as wrong accounts and root. The plan's caller identity confirmed this role. No credentials or raw plan values are published.

## Proposed changes

The plan has **16 creates, zero updates and zero deletions**. Terraform counts configuration objects separately:

- One protected, private, versioned AES256 telemetry bucket with SSE-C blocked, owner enforcement, public access blocking and service delivery/TLS policy.
- One AWS Config service-linked role, S3-only recorder, delivery channel and recorder-status object; two research-tag-scoped S3 Config rules.
- One single-region CloudTrail management-event trail with log-file validation, no data events or Insights.
- One standalone Security Hub CSPM enrollment, with default standards and automatic new controls disabled.
- One account-wide $25 monthly alert budget with actual 50/80/100-percent and forecast 100-percent thresholds, using the privately supplied email address.
- One local Terraform identity guard.

Config recording and CloudTrail logging remain **off**. No FSBP subscription or control resources are in this plan. No EC2, EKS, Lambda, NAT gateway, KMS key, collector or research scenario is deployed. Enrollment may create AWS-managed Security Hub service-linked resources indirectly; the deployment role only permits the reviewed Config/Security Hub service-linked role names. Their AWS-managed permissions are independent of the deployment role boundary.

## Costs and shared-account effects

All seven retained Ohio public-price rates were refreshed through read-only AWS Price List queries at `2026-10-27T04:14:51Z`; the rates were unchanged. This is not a bill forecast or spending cap. Monitoring-only budgets have no additional budget charge; this plan does not enable budget actions or reports. See [AWS Budgets pricing](https://aws.amazon.com/aws-cost-management/aws-budgets/pricing/).

As a storage/request illustration only, one retained GB-month plus 10,000 PUT/LIST and 10,000 GET requests models $0.077 using the refreshed Ohio rates. This assumes no metered Config items/evaluations, CSPM checks or additional paid CloudTrail event copies. Service initialization, incidental evaluations, object versions, account activity, taxes or unmodeled charges can increase the bill. No free trial or credits are assumed. See [S3 pricing](https://aws.amazon.com/s3/pricing/), [Config pricing](https://aws.amazon.com/config/pricing/), [Security Hub pricing](https://aws.amazon.com/security-hub/pricing/) and [CloudTrail pricing](https://aws.amazon.com/cloudtrail/pricing/).

The budget covers unrelated account spending too, and alerts can be delayed; it cannot stop charges. Recording is paused, but Config's future scope is all Ohio S3 buckets and CloudTrail's future management-event scope includes unrelated account metadata. Existing application resources are not imported or changed by this plan. Activation requires a separate reviewed plan and permissions update; the current deployment role cannot start recording/logging.

## Validation and execution gate

Terraform validation and seven mocked baseline safety runs passed, including rejection of unbounded users. The actual plan was inspected privately: all actions are creates, the expected restricted role is used, collection is false, both default CSPM switches are false, and the budget is $25. A successful plan does not prove every create API will be permitted or every service delivery path operational.

Approval must cover this digest and paused-only scope. Once approved, reverify account identity, source/plan digest and state freshness; apply only the saved plan. If permissions or service behavior cause a partial failure, retain remote state and report actual created resources. Do not broaden permissions, enable collection, or run an unreviewed replacement plan.

After deployment, read back recorder/trail stopped status, CSPM settings, bucket protections and budget/notification configuration; require a no-change plan. Confirm actual email receipt with the user when AWS sends a notification; configuration alone does not prove delivery. Preserve raw verification privately. A paused baseline is not yet a validated research instrument. Freeze and independently review the scenario catalog before pilot collection; keep pilot evidence separate from confirmatory data.
