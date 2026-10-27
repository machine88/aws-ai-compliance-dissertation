# Implementation plan — pending review

## Verified status (2026-10-26)
Repository cloned at 4e239a8. Initial contents: README and .gitignore only.
Default STS identity query failed: credentials unavailable. Account 653464153304 is the requested target, not a verified identity. No AWS resources changed.
No final proposal exists in the workspace. Referenced conversation has an attachment marker but no accessible attachment. Its assistant summaries are context, not methodological authority.
Terraform, GitHub CLI and R are unavailable locally. GitHub read access works; authenticated write access is unverified.

## Phase 1 — local foundation
1. Obtain final proposal, record SHA-256, and extract a page-referenced requirements matrix: questions, units, services, features, adaptation limits, partitions, estimands, censoring and exclusions.
2. Verify target-account short-lived identity and inspect regional Config recorders/delivery channels, Security Hub configuration and organization ownership, CloudTrail trails, billing controls and existing state. Read only. Do not import or replace shared resources without review.
3. Establish tested evidence contracts, independent scenario specifications, immutable protocol versioning and offline fixtures.
4. Review a provider-validated Terraform plan and itemized estimate before deployment.

## Permissions and isolation
Use AWS IAM Identity Center/SSO or an assumed research role; no root credentials, long-lived keys in files, or secrets in chat. Inspection role: sts:GetCallerIdentity, config:DescribeConfigurationRecorders, config:DescribeDeliveryChannels, config:DescribeConfigurationRecorderStatus, securityhub:DescribeHub, securityhub:GetEnabledStandards, cloudtrail:DescribeTrails, budgets:ViewBudget and ce:GetCostAndUsage, with unavoidable list/describe wildcard resources documented. No automatic role creation or administrator access.
Deployment role must have a reviewed action/resource allowlist for research-prefixed buckets, service roles, trail and selected monitoring configuration. Restrict iam:PassRole to the dedicated Config role and service. Separate state access; session duration <=1 hour. Deny organization changes, credential creation and unrelated resource deletion.
Use a dedicated region, research tags and resource namespace. Account-wide monitoring may inspect unrelated workloads: inventory and agree scope first. Never create public buckets, live exposed workloads, EKS clusters, NAT gateways or public credentials for a scenario.

## Budget proposal — not approved
Propose USD 25 monthly research ceiling, USD 5 first-pilot review threshold, 24-hour initial deployment window and one region. These are proposed spending limits, not price estimates or guaranteed caps. Before approval calculate Config recording/evaluations, Security Hub checks, CloudTrail events, S3 requests/storage and state costs from current regional rates and observed account volume. Account-wide monitoring can dominate costs.
Configure forecast and actual alerts at 50%, 80% and 100% to a user-selected destination. AWS Budgets alerts are delayed and do not stop spending. Require a teardown appointment, manual cost review before each run and no continuous compute. Keep data events and broad resource recording disabled unless protocol requires and estimate includes them. Preserve evidence during teardown.

## Terraform state and deployment gate
Use separately bootstrapped private S3 state storage, encryption, versioning, TLS enforcement and native lockfiles. Separate keys for bootstrap, baseline, development, pilot and confirmatory, including account and region. No credentials in backend configuration. No local state committed. Retention and recovery documented before use.
No apply automation in Phase 1. Required gate: verified target ARN/account, final proposal traceability, approved region/scope, least-privilege policies, existing-service disposition, budget estimate and alert destination, state recovery test, validated saved Terraform plan, teardown plan and explicit user approval of that plan. Any later plan changes require renewed review. No deployment approval has been given.

## Next implementation phases
Phase 2: version-pinned Terraform baseline for selected AWS Config types/rules, Security Hub CSPM controls and CloudTrail management telemetry to private encrypted versioned storage. Inspect existing services first; explicit adopt/import versus isolated-create decision. Validate service delivery policies and log integrity. Commit provider lock file after initialization.
Phase 3: independently authored paired compliant/noncompliant scenarios with assessment citations, resource-state predicates, independent reviewer signoff, trigger and recovery recipes. Freeze ground truth before either monitor runs. No monitor output establishes truth. Candidate services and mappings await proposal.
Phase 4: shared timestamped telemetry normalization, Isolation Forest with fixed feature schema/seed and training-only fitting, bounded adaptation with versioned limits and audit logs, deterministic requirement mapping that returns unknown for missing evidence. Anomaly score alone must never imply noncompliance. Baseline and AI consume matched conditions with measured availability delays.
Phase 5: instrument pilots; store raw evidence, checksums, collection times, event times, trial IDs, model/feature/mapping versions and failures. Validate latency clocks and missing-output handling. Pilot data cannot become confirmatory data.
Phase 6: proposal-aligned R simulation power analysis for clustered paired outcomes and censored detection latency; validate type-I error and power across assumed effect sizes/ICC/censoring. Freeze sample size and protocol before held-out runs. Implement mixed-model and latency analyses only after checking final proposal; no invented results.

## Sources
https://docs.aws.amazon.com/securityhub/latest/userguide/securityhub-setup-prereqs.html
https://developer.hashicorp.com/terraform/language/backend/s3
https://docs.aws.amazon.com/prescriptive-guidance/latest/terraform-aws-provider-best-practices/backend.html
