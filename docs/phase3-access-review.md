# Restricted baseline access: pending approval

Only the state bucket has been deployed. This change prepares a separate deployment role; it does not authorize its creation, state migration, or monitoring deployment.

The access root creates three managed policies, one role, two policy attachments, and a local identity guard. Only IAM user `martin-morales-personal` in account `653464153304` is trusted to assume the role, with a maximum one-hour session. No access keys or new users are created. The existing provisioning identity creates the role after approval; the role cannot provision itself or change its boundary.

The baseline identity policy is preserved from IAM Policy Autopilot 0.3.0 output for the paused baseline preview (16 creates, no updates or deletions). Its broad grants are unsafe alone. Terraform attaches the mandatory permissions boundary at role creation. Never attach the generated policy to another identity without equivalent reviewed restrictions. A separate policy supplies state-backend access and scoped provider metadata reads omitted by resource-plan generation. No AdministratorAccess or account-wide ReadOnlyAccess policy is attached.

The boundary restricts writes to the named Ohio telemetry bucket, baseline state key and lock, research trail, Config instruments, default Ohio CSPM hub, named budget, and required Config/Security Hub service-linked roles. Config APIs without resource-level authorization require a regional wildcard allowance. Config rule creation requires the Project request tag; rule IDs are assigned by AWS, so their ARN family uses a wildcard. Budgets ModifyBudget also permits modifying or deleting the named budget; IAM cannot distinguish those operations using that action. Service-linked roles have AWS-managed permissions independent of this boundary.

The role cannot start CloudTrail or the Config recorder, launch compute, delete state, access unrelated S3 objects, pass an administrator role, or modify its own permissions. Changes that enable collection or grant activation permissions need another reviewed plan. Paused infrastructure is not a guarantee of zero charges: storage and service initialization behavior still require cost review. The proposed $25 budget sends alerts and does not cap spending.

Seven read-only AWS SimulateCustomPolicy cases passed using the actual proposed identity policies and boundary; results are in `access-simulation.json`. These tests check specific permissions, not complete provider compatibility, organizational controls, or resource-policy behavior. Terraform validation and a fully mocked role test additionally check boundary attachment, trust principal, and session duration. Literal boundary actions were checked against the AWS service authorization reference.

## Next deployment gates

1. Review and approve the saved access-root plan before creating the role. No automatic apply or merge is included.
2. Review state migration separately: retain a mode-600 local backup; migrate bootstrap state to its own key in the existing encrypted, versioned state bucket; verify lineage, serial, resource identities and a no-change plan. Access and baseline state must use distinct keys. Do not delete local backups until migration is verified.
3. Configure a local role profile without exposing credentials, verify its caller identity and expected boundary, then initialize the isolated baseline backend. Baseline backend access must use the restricted role. Use only the default Terraform workspace; the backend example reserves a separate workspace prefix but grants no workspace state writes.
4. Generate and review a fresh remote-backend baseline plan. The existing local-backend preview is not an apply artifact. Confirm no changes to existing account resources, collection remains false, the private budget recipient is correct, and disclose costs before approval.
5. Enable collection only after a further explicit approval. Freeze and independently review the scenario catalog before pilot or confirmatory runs; no research results have been collected.

References: [AWS policy evaluation](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_evaluation-logic.html), [AWS service authorization reference](https://docs.aws.amazon.com/service-authorization/latest/reference/), [Terraform S3 backend permissions](https://developer.hashicorp.com/terraform/language/backend/s3#permissions-required).
