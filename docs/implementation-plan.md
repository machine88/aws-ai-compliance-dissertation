# Implementation plan — pending review

## Verified status (2026-10-26)
Repository cloned at 4e239a8. Initial contents: README and .gitignore only.
AWS identity verified through STS: account 653464153304, IAM user martin-morales-personal, profile dissertation; default region us-east-2. Root sessions were cleared and are not used. AWS Agent Toolkit installed locally; account-service inventory and service permissions remain unverified. No research resources deployed.
Final proposal read and SHA-256 recorded: `99ad4b0aa5e1af82346f5e8b0bb1e8388b48726dc8815b8f68bddf3df896f5db`. See proposal-traceability.md for section-level requirements and unresolved implementation details.
Terraform and R have not been installed or validated. GitHub connector authenticated as machine88; draft PR #1 contains the initial foundation.

## Phase 1 — local foundation
1. Maintain final proposal SHA-256 and section-referenced requirements matrix: questions, units, services, features, adaptation limits, partitions, estimands, censoring and exclusions.
2. Verify target-account short-lived identity and inspect regional Config recorders/delivery channels, Security Hub configuration and organization ownership, CloudTrail trails, billing controls and existing state. Read only. Do not import or replace shared resources without review.
3. Establish tested evidence contracts, independent scenario specifications, immutable protocol versioning and offline fixtures.
4. Review a provider-validated Terraform plan and itemized estimate before deployment.

## Permissions and isolation
Use AWS IAM Identity Center/SSO or an assumed research role; no root credentials, long-lived keys in files, or secrets in chat. Inspection role: sts:GetCallerIdentity, config:DescribeConfigurationRecorders, config:DescribeDeliveryChannels, config:DescribeConfigurationRecorderStatus, securityhub:DescribeHub, securityhub:GetEnabledStandards, cloudtrail:DescribeTrails, budgets:ViewBudget and ce:GetCostAndUsage, with unavoidable list/describe wildcard resources documented. No automatic role creation or administrator access.
Deployment role must have a reviewed action/resource allowlist for research-prefixed buckets, service roles, trail and selected monitoring configuration. Restrict iam:PassRole to the dedicated Config role and service. Separate state access; session duration <=1 hour. Deny organization changes, credential creation and unrelated resource deletion.
Use a dedicated region, research tags and resource namespace. Account-wide monitoring may inspect unrelated workloads: inventory and agree scope first. Do not create public buckets, live exposed workloads, NAT gateways or public credentials for a scenario. EKS is required by the final proposal but deferred to a separately costed and approved phase; no EKS cluster is authorized in Phase 1.

## Budget proposal — not approved
Propose USD 25 monthly research ceiling, USD 5 first-pilot review threshold, 24-hour initial deployment window and one region. These are proposed spending limits, not price estimates or guaranteed caps. Before approval calculate Config recording/evaluations, Security Hub checks, CloudTrail events, S3 requests/storage and state costs from current regional rates and observed account volume. Account-wide monitoring can dominate costs.
Configure forecast and actual alerts at 50%, 80% and 100% to a user-selected destination. AWS Budgets alerts are delayed and do not stop spending. Require a teardown appointment, manual cost review before each run and no continuous compute. Keep data events and broad resource recording disabled unless protocol requires and estimate includes them. Preserve evidence during teardown.

## Terraform state and deployment gate
Use separately bootstrapped private S3 state storage, encryption, versioning, TLS enforcement and native lockfiles. Separate keys for bootstrap, baseline, development, pilot and confirmatory, including account and region. No credentials in backend configuration. No local state committed. Retention and recovery documented before use.
No apply automation in Phase 1. Required gate: verified target ARN/account, final proposal traceability, approved region/scope, least-privilege policies, existing-service disposition, budget estimate and alert destination, state recovery test, validated saved Terraform plan, teardown plan and explicit user approval of that plan. Any later plan changes require renewed review. No deployment approval has been given.

## Next implementation phases
Phase 2: version-pinned Terraform baseline for selected AWS Config types/rules, Security Hub CSPM controls and CloudTrail management telemetry to private encrypted versioned storage. Inspect existing services first; explicit adopt/import versus isolated-create decision. Validate service delivery policies and log integrity. Commit provider lock file after initialization.
Phase 3: independently authored paired compliant/noncompliant scenarios with assessment citations, resource-state predicates, independent reviewer signoff, trigger and recovery recipes. Freeze ground truth before either monitor runs. No monitor output establishes truth. Required final-design services are EC2, S3, Lambda, EKS, VPC and IAM. Catalog sources and assessment mappings require separate verification. Approximately half of scenarios must be rule-matched and half combinatorial/drift; preserve compliant/noncompliant balance. Hash and freeze the catalog before pilot; independent AWS-security review is required before confirmatory collection.
Phase 4: shared timestamped telemetry normalization, Isolation Forest with fixed feature schema/seed and training-only initial fitting, bounded adaptation with versioned limits and audit logs, deterministic requirement mapping that returns unknown for missing evidence. Anomaly score alone must never imply noncompliance. Baseline and AI consume matched conditions with measured availability delays.
Phase 5: instrument pilots; store raw evidence, checksums, collection times, event times, trial IDs, model/feature/mapping versions and failures. Validate latency clocks and missing-output handling. Pilot data cannot become confirmatory data.
Phase 6: proposal-aligned R simulation power analysis for clustered paired outcomes and censored detection latency; validate type-I error and power across assumed effect sizes/ICC/censoring. Freeze sample size and protocol before held-out runs. Use at least 1,000 simulations per candidate design, target power >=.80 with familywise alpha .05 and Holm across five hypotheses, initially plan binary OR 1.50. Separately verify RMST power at 1,800s with 120s important difference and 15% censoring; vary censoring 5–30% and difference 60–180s. Select the larger design requirement. Use four binomial logit GLMMs and paired clustered RMST in R; report OR/effects, 95% intervals and Holm-adjusted p-values. No sample size is yet established.

## Sources
https://docs.aws.amazon.com/securityhub/latest/userguide/securityhub-setup-prereqs.html
https://developer.hashicorp.com/terraform/language/backend/s3
https://docs.aws.amazon.com/prescriptive-guidance/latest/terraform-aws-provider-best-practices/backend.html

## Scientific readiness gates
Catalog must be externally sourced, balanced, versioned and hashed before pilot; reviewer signoff is required before confirmatory. Keep trial phase (development/pilot/confirmatory) distinct from learning role (training/validation_adaptation/held_out); no pilot record may become confirmatory evidence. Preserve related-family assignments, batch eligibility and scoring-before-adaptation order. Mapping changes and administrative baseline corrections invalidate affected trials and require documented repeats, never removal for poor performance. Complete the open decisions in proposal-traceability.md before locking a confirmatory protocol.
