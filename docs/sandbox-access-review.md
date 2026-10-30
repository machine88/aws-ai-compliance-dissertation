# Dedicated sandbox access proposal

Status: the reviewed six-create IAM saved plan was explicitly approved, applied and independently verified on October 30, 2026 (America/Chicago). A follow-up access-root plan reported no changes. This stage created IAM access only. It does not create the S3 sandbox, change versioning, activate monitoring, run a capture, or authorize a research trial.

## Why a separate role

Extending the existing baseline boundary would exceed IAM's single managed-policy size limit. The deployed `dissertation-sandbox-deploy` role instead has its own 3,958-character boundary, generated identity policy and exact state/read policy. The existing baseline role, trust, boundary and two attached policies are unchanged. The three new policy documents fit the managed-policy limit.

The role trusts only the existing named IAM user in account 653464153304, requires its boundary from creation and limits sessions to one hour. It can manage the reserved Ohio sandbox bucket configuration and the exact `development-sandbox` state/lock keys. State deletion is not granted; lock deletion is. Explicit denials block other storage and actions outside the dedicated ceiling. Bucket configuration writes remain subject to reviewed Terraform plans; IAM does not prove that a permitted API payload preserves every desired setting.

The raw Autopilot 0.3.0 identity policy is retained unedited. Its broad pass-role, access-point, object-tagging, Object Lambda and S3 Express candidates do not become effective grants through the dedicated boundary. The reproducible builder derives the bucket allowance by intersecting generated actions with the previously reviewed bucket ceiling, then copies the established exact-key backend pattern for the new state namespace. No hand-inferred provider-to-IAM mapping replaces Autopilot.

## Plan and verification

The private local-backend S3 preview contains six S3 creates and one Terraform guard. It used the existing bounded role for planning, with the original backend removed and that transformation recorded. It is not a deployable remote-state plan. The S3 source now binds the dedicated role; a real protected-backend S3 plan has been prepared under that role and remains unapplied. Neither the preview nor its provenance hash proves human approval.

The approved and applied access-root saved plan used existing protected access state and contained **six creates, zero updates and zero deletes**:

- Three managed policies: generated candidate, dedicated boundary and exact state/read policy.
- One bounded `dissertation-sandbox-deploy` role.
- Two policy attachments to that new role.

Live read-only inspection confirmed the expected non-root source identity and that the existing baseline policy documents match the repository, with two managed attachments and no inline policies. IAM custom-policy simulations checked 94 resource-specific decisions, including intended bucket configuration/state operations and denial of unrelated buckets, access points, sandbox object bodies/tagging, baseline state, wrong-region configuration and privilege-changing actions. The simulation did not execute those actions. Its scope is the supplied policies and contexts; it is not an attestation of all live SCP/resource/session policies or guaranteed apply success. Raw inventory, simulation results, saved plans and exact bindings stay private.

Three Python regression tests check reproduction, policy size/provenance, exact object exceptions and unsupported privileges. Mocked Terraform checks verify separate boundary attachment, trust, session limits and the updated S3 role binding. No new scientific claims follow from these administrative checks.

## Approval stages and recovery

1. Completed: explicit approval and application of the exact six-create IAM plan after identity, source, runtime and plan hash checks. Code merge alone did not authorize that apply.
2. Completed: exact trust, one-hour limit, dedicated boundary, two attachments, no inline policies and unchanged baseline documents verified through AWS MCP. The post-apply no-change plan passed; candidate simulation results remain limited to their supplied contexts.
3. Prepared: the S3 root was initialized against its unique protected default-workspace backend using the new role. The real saved plan contains six S3 creates and one Terraform guard, zero updates and zero deletes. Reserved bucket/state names were absent at preflight; current regional prices were retrieved. Separate bucket deployment approval is pending.
4. Keep the empty bucket secure after deployment. Reader/injector permissions, collector allowlists, executable trigger/restoration code and a separately approved development run are still required before mutation or capture.

If IAM creation fails partway, retain Terraform state and the failure record, inspect actual attachments/boundaries and prepare a reviewed correction. Do not switch the S3 provider to the provisioning user, attach administrator access or remove a boundary. To withdraw unused access later, first verify the role has no active experiment or managed S3 resources, then review a separate IAM removal plan; do not destroy protected state or evidence as part of role cleanup.

AWS lists IAM at no additional charge; this plan adds no compute, bucket or monitoring service. Existing S3 state requests/storage and CloudTrail activity remain billable dimensions. The $100 monthly account alert stays unchanged and is not a spending cutoff. See [IAM FAQ](https://aws.amazon.com/iam/faqs/) and [IAM simulation limitations](https://docs.aws.amazon.com/IAM/latest/APIReference/API_SimulateCustomPolicy.html).
