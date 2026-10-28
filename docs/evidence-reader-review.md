# Reader access proposal: offline candidate, not deployment approval

The encrypted snapshot collector is merged. This proposal adds a separate Terraform root for its dedicated `dissertation-evidence-reader` role. No IAM role, policy, local AWS profile, certificate or research resource is created by committing/merging this code. Monitoring stays paused.

## Proposed change

Four IAM resources: one role, its mandatory permissions-boundary policy, the generated identity policy, and one attachment. A fifth Terraform-only identity guard records the provisioning check. Trust is limited to the existing `martin-morales-personal` IAM user in account 653464153304; the role has one-hour sessions. No user-policy attachment, access key, role chaining or deployment-role change is included. The local provisioning guard requires the exact reviewed user and default workspace. Provider account restrictions add an independent account check.

The identity policy is unedited IAM Policy Autopilot 0.3.0 output. The collector dispatches most operations dynamically, so `scripts/export_reader_policy_input.py` expands both maintained fixed plans into explicit analysis-only SDK calls. It does not execute them. An AST regression test compares service, operation and parameters against the runtime plans, including pagination targets. Pass the real SDK source and this expansion to the analyzer; never run the generated analysis source itself.

Reproduce from the repository root (use an absolute new path for the output):

```sh
python scripts/export_reader_policy_input.py --output /private/tmp/new-reader-analysis.py
DISABLE_IAM_POLICY_AUTOPILOT_TELEMETRY=true uvx iam-policy-autopilot==0.3.0 generate-policies \
  "$PWD/scripts/collect_snapshot.py" "$PWD/research/aws_reader.py" \
  /private/tmp/new-reader-analysis.py \
  --region us-east-2 --account 653464153304 \
  --service-hints s3 config securityhub cloudtrail sts --pretty
```

Do not add `--upload-policies`. Generated broad resource patterns are preserved for audit and intersected with the separately authored boundary. The boundary limits S3 metadata to the two reviewed bucket ARNs, Config evaluations to two required verified rule ARNs, recorder reads to its required verified ARN, Security Hub CSPM to the Ohio hub/default ARN and trail status to the named trail. All these allows require Ohio endpoints. An explicit NotAction deny prevents writes, object reads, credential access and role assumption even if a later identity policy mistakenly adds them. The boundary is not itself a grant.

## Unavoidable breadth and limitations

`config:DescribeDeliveryChannels` has no resource-level scope, so its allow uses Resource `*` with the Ohio condition; the collector now requests only the named research channel. Security Hub GetFindings authorization is at hub level, not bucket/control level. The role can read other findings in that hub if used outside the collector. Bucket/account/control filters are application safeguards, not IAM isolation. Config evaluation pages may include other resources evaluated by the two named rules. Raw responses must remain private and encrypted.

STS identity uses Resource `*`; GetCallerIdentity does not depend on granting that action. The generated identity policy retains analyzer warnings about wildcard resources. This proposal does not claim a full account audit or validate organizational policies, resource-policy grants, propagation, or live API behavior. The boundary's resource restrictions are primarily allow intersections; the explicit deny is an action ceiling, not a claim that every possible future resource-based grant is neutralized.

The two Config rule ARNs and recorder ARN intentionally have no defaults. Their service-assigned identifiers must be discovered through read-only AWS calls and checked against the deployed names before a real plan. Synthetic test identifiers are never deployment inputs. No guessed IDs or policy wildcard substitutes are allowed for these variables. See official [Config authorization reference](https://docs.aws.amazon.com/service-authorization/latest/reference/list_awsconfig.html) and [Security Hub authorization reference](https://docs.aws.amazon.com/service-authorization/latest/reference/list_awssecurityhub.html).

## State and cost

State uses the existing protected S3 bucket under a new `reader-access/terraform.tfstate` key, separate from bootstrap/access/baseline state. It uses encryption, versioning inherited from the bucket and native lockfiles. No existing root is moved or imported. Existing state policies and the deployment role are unchanged. The provider and Terraform versions stay pinned; CI initializes with backend disabled and uses synthetic providers.

The IAM proposal creates no compute, monitoring subscription or running workload. Existing S3 state storage/requests remain ordinary charges, and future approved snapshot reads may add service request/management-event costs. No new numeric spending estimate or hard cap is claimed. The existing $100 monthly alert budget remains the cost control; notification delivery still needs verification. Removing the reader role/policies later must preserve evidence and other state keys.

## Required gate before any apply

1. Restore AWS MCP availability and verify actual STS account/non-root provisioning identity. This change attempted the official connection twice; both returned Unknown tool before any AWS API ran.
2. Inspect exact Config ARNs, role-name/policy-name collisions and the new state-key destination through read-only calls. Do not replace an existing externally managed role.
3. Run IAM policy validation and live allowed/denied simulations, including unrelated buckets/rules, state objects, IAM writes, service activation and other regions. Preserve raw outputs privately. Simulation is not a live-access guarantee.
4. Produce a fresh private saved plan with verified inputs: four IAM creates plus the guard, no updates/deletions or service activation. Check its digest, caller, state routing and costs. Any unexpected difference requires review.
5. Obtain explicit user approval of that concrete plan before apply. Then verify the assumed reader identity and actual permitted/denied reads before approving any collection. Configure a temporary-role local profile separately, without passwords or keys in chat.

Offline checks: Terraform validation and two mocked reader tests; complete Python suite and function documentation checks. No real saved deployment plan, live policy simulation, certificate or reader session exists from this change. This document is not a request to approve an incomplete live plan.
