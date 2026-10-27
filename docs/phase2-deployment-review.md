# Phase 2 monitoring baseline review

Historical Phase 2 review. Bootstrap, restricted-role deployment and state migration are now complete; see `state-migration-completed.md`. The current paused monitoring plan is in `paused-baseline-approval.md` and has not been applied. Original review status: implemented and tested offline; no deployment approved or performed. This PR does not freeze the experimental catalog or authorize pilot or confirmatory collection.

## Proposed resources

- Bootstrap: one separate Ohio state bucket, blocked public access, ownership enforcement, SSE-S3 encryption, versioning, TLS-only policy and deletion protection.
- Baseline: one dedicated private versioned telemetry bucket, AWS Config service-linked role, one S3-only continuous recorder and delivery channel, two tag-scoped direct Config rules, one regional management-event CloudTrail with log-file validation, standalone Security Hub CSPM with default standards and automatic new controls disabled, and one account-wide monthly budget with four alert thresholds.
- Default collection is paused. Config recording and trail logging remain off and FSBP is not subscribed until enable_collection is explicitly reviewed and enabled. Even paused foundation deployment involves AWS API changes and may incur storage/request charges; it is not authorized by code review or merging.
- Proposed initial instrument controls are S3.5 (TLS-only bucket policy) and S3.8 (all four bucket public-access-block flags). These are not the completed scenario catalog and do not replace independent NIST assessment mapping or the balanced catalog required by the proposal.

## Shared-account boundaries

The code neither imports nor modifies existing application buckets. Verify their locations and shared-account effects before deployment. Config is regional but records every S3 bucket in Ohio, including the state and telemetry buckets and future unrelated buckets. Tag filters limit only the two directly managed Config rules. Security Hub controls are regional and cannot be restricted by those Config rule tag filters. CloudTrail management events can include unrelated account API metadata and global-service activity. Collectors must admit only research resource IDs, verified time windows and scenario-attributable events into experimental data; raw account telemetry is not automatically an experimental observation.

A new FSBP subscription initially enables the standard's controls before Terraform disables those outside the 346-ID regional snapshot allowlist. This transient broad evaluation can produce checks and charges, and may involve account/global conditions. It must be included in approval and observed before instrument validation. auto_enable_controls=false prevents later new controls from silently changing the baseline. Refresh the public definitions immediately before deployment, compare the snapshot, and verify that only S3.5 and S3.8 are enabled before collection. No findings are suppressed or archived.

## State isolation and recovery

Bootstrap initially uses ignored local bootstrap.tfstate. Keep its protected backup until a separately reviewed migration to the new bucket completes. Baseline uses an S3 backend with native lockfiles, encryption, expected account allowlist and a unique key containing account, region and baseline phase. Pilot and confirmatory resource states must use separate keys later; this does not authorize their creation now. State and evidence buckets have prevent_destroy=true and force_destroy=false.

Restrict state access to the exact state key and its .tflock key. State users need GetObject/PutObject on state and lock, DeleteObject only on the lock, and prefix-scoped ListBucket. Do not grant DeleteObject on state. Verify version recovery before operational use. State is sensitive even with encryption; never commit state, plan JSON, local variables or raw evidence. No lifecycle expiration deletes evidence or state versions.

## Permissions review still required

No IAM administrator policy is included or attached by this PR. The recorder uses AWS's service-linked role rather than a researcher-authored broad service role. Its AWS-managed read scope is account-wide and must be acknowledged. S3 delivery grants restrict CloudTrail by exact trail ARN and Config by account, region and object prefix; neither grants cross-account access. The deployment identity is constrained by account and a root-session guard, but those guards are not a least-privilege identity policy.

Before deployment, generate the deployment role policy from the real reviewed Terraform plan, using the IAM policy-generation workflow. Review required S3 configuration actions only for the two named buckets; Config actions only for the named recorder, channel and two rules where resource scoping is supported; Security Hub actions only in Ohio and approved standard/control ARNs; CloudTrail actions only for the named trail; Budgets actions only for the named budget; and service-linked-role creation conditioned on config.amazonaws.com or securityhub.amazonaws.com. Scope iam:PassRole to the exact Config service-linked role and config.amazonaws.com if the final provider plan requires it. Document actions that require Resource="*". No role, policy attachment or permission change has occurred.

## Cost assumptions and controls

Public Ohio pricing was queried read-only on October 26, 2026 through AWS Price List GetProducts. protocol/baseline-price-snapshot.json retains selected SKUs, publication dates and per-unit first-tier prices. scripts/estimate_baseline_cost.py uses Decimal arithmetic and explicit usage quantities; it never reads billing data or creates services.

| Planning example | Config items | Direct Config evaluations | CSPM checks including initialization | Retained GB-months | S3 PUT/LIST | S3 GET | Modeled cost |
|---|---:|---:|---:|---:|---:|---:|---:|
| Initial 24-hour session with one month retention | 100 | 200 | 500 | 1 | 10,000 | 10,000 | $1.077 |
| Monthly usage illustration | 1,000 | 2,000 | 5,000 | 1 | 10,000 | 10,000 | $10.077 |

These are assumed-usage illustrations, not measured forecasts, complete bill estimates or guaranteed limits. They assume zero additional paid management-event copies and standalone CSPM check pricing, with no free trial or credits assumed. Additional telemetry volume, version history, repeated evaluations, initial broad checks, data transfer, taxes and unrelated account usage can increase the total. Refresh rates, verify the current CSPM subscription/billing model and management-event copy eligibility, and replace usage assumptions before approval. Security Hub V2 Essentials, GuardDuty, EKS, EC2, Lambda, NAT gateways, KMS keys, data events, Insights, CloudTrail Lake, audit-manager assessments and collectors are not provisioned by this phase.

Proposed account-wide monthly alert budget: $25, with actual alerts at 50%, 80% and 100%, plus forecast at 100%. Alert recipient is provided privately in ignored local-review.tfvars. Account-wide alerts include unrelated spending and are delayed; they do not enforce a spending cap. Proposed first-session review threshold is $5 and collection duration 24 hours; neither is an automatic cutoff. Schedule shutdown and verify it manually. Enabling cost-allocation tags is not performed.

## Approval gate and execution sequence

Merging this PR approves source changes only. No workflow applies infrastructure.

1. Reverify non-root account identity, inventory, regional FSBP definitions, billing model and scoped deployment permissions. Review the cost estimate, budget destination, 24-hour shutdown responsibility and retention.
2. Prepare and review a real saved bootstrap plan. Explicit user approval must name its digest and deployment scope before it is applied.
3. After approved bootstrap only, test protected state recovery and review state migration. Configure the isolated baseline backend and prepare a fresh real baseline plan; do not reuse a mock test plan as a deployment plan.
4. Inspect creates, updates, replacements, deletions, permissions and costs in that saved plan. Obtain explicit approval for its digest before applying. Any changes require a new reviewed plan.
5. Initially deploy with collection paused; verify budget notifications and service delivery configuration. Review a separate activation plan, including the transient FSBP checks, before starting collection. Confirm service roles, bucket delivery, trail validation and recorder status. Do not call a paused baseline operational.
6. Verify actual enabled controls match the snapshot allowlist. Validate instruments after the catalog is frozen and hashed. Pilot data remain excluded from confirmatory evidence; the proposal's 30-minute observation feasibility must be tested.

## Shutdown and evidence retention

A reviewed plan with enable_collection=false stops Config recording, disables trail logging and unsubscribes FSBP. This removes the baseline standard/control resources managed by this configuration; it is an administrative baseline change, so any active trial must be invalidated and repeated under a locked configuration. Verify stop status and late delivery; retention still accrues S3 cost. Security Hub account enrollment, service role, budget, and protected buckets remain. Full teardown needs a separate reviewed change that removes deletion guards only after evidence/state export and retention approval; never force-empty buckets.

## Validation and remaining work

Both Terraform roots validate with pinned AWS provider 6.36.0 and lockfiles. Seven mocked Terraform runs verify baseline and state safeguards without AWS calls. Seven Python tests cover evidence isolation, account guard and exact cost arithmetic. Function docstrings are checked automatically. CI runs the same offline checks without AWS credentials or deployment permissions.

Live service permissions, real saved deployment plans, state recovery, budget delivery, CSPM configuration timing and CloudTrail/Config delivery are not validated yet. The complete scenario catalog, independently reviewed ground truth, telemetry collectors, Isolation Forest, bounded adaptation, deterministic mapping and R power/inferential analyses remain subsequent work.

## References

- AWS Config delivery policy: https://docs.aws.amazon.com/config/latest/developerguide/s3-bucket-policy.html
- CloudTrail delivery policy: https://docs.aws.amazon.com/awscloudtrail/latest/userguide/create-s3-bucket-policy-for-cloudtrail.html
- S3 controls: https://docs.aws.amazon.com/securityhub/latest/userguide/s3-controls.html
- FSBP: https://docs.aws.amazon.com/securityhub/latest/userguide/fsbp-standard.html
- S3 state locking: https://developer.hashicorp.com/terraform/language/backend/s3
- Terraform mocks: https://developer.hashicorp.com/terraform/language/tests/mocking
- Pricing: https://aws.amazon.com/config/pricing/ and https://aws.amazon.com/security-hub/pricing/ and https://aws.amazon.com/s3/pricing/ and https://aws.amazon.com/cloudtrail/pricing/
