# Proposed history-inspection access

This source change prepares an update to the existing dedicated reader role's two managed policies. It does not apply that update or authorize live collection. The existing trust, maximum session duration, protected state root and metadata resource scopes remain unchanged. No role replacement, user policy, access key, monitoring activation or running workload is proposed.

The unedited identity-policy output is regenerated with IAM Policy Autopilot 0.3.0 from both collectors and the tested deterministic SDK-call expansion. The only added action is `cloudtrail:LookupEvents`; no existing actions are removed. The separately authored boundary adds an Ohio-only allow for that action and retains the explicit deny for all other actions outside the generated read set. Stored S3 object content, IAM changes, service activation, paid CloudTrail queries and role chaining stay outside that set.

## Scope that must be approved

LookupEvents has no resource-level bucket or trail scope in AWS IAM. Its Resource must be `*`, limited here by the requested-region condition. If applied, this role can inspect available regional event history beyond the selected research bucket, and an operator outside the collector could choose different filters. The collector's EventName/time/bucket restrictions do not turn into IAM enforcement. This broader read capability is why a fresh saved-plan review and explicit approval are required before applying.

The collector encrypts bounded SDK-visible pages before filtering and never prints event bodies. Those pages can contain other resources' metadata. Recipient-certificate readiness and approval of a concrete development capture remain separate from permission approval. The command still cannot attest provider delivery completeness or establish prospective detection latency. See `event-history-collector.md`.

## Reproducible generation

From the repository root, write a fresh analysis-only input and run the analyzer. Never execute the generated source or add an upload option:

```sh
python scripts/export_reader_policy_input.py --output /private/tmp/new-history-policy-input.py
DISABLE_IAM_POLICY_AUTOPILOT_TELEMETRY=true uvx iam-policy-autopilot==0.3.0 generate-policies \
  "$PWD/scripts/collect_snapshot.py" "$PWD/scripts/collect_event_history.py" \
  "$PWD/research/aws_reader.py" "$PWD/research/event_history.py" \
  /private/tmp/new-history-policy-input.py \
  --region us-east-2 --account 653464153304 \
  --service-hints s3 config securityhub cloudtrail sts --pretty
```

The fixed January interval in the expansion is only synthetic static-analysis input; no history is queried. AST parity tests cover both maintained snapshot and history request plans. `protocol/history-reader-policy-generation.json` records tool/source/policy hashes and analyzer warnings. The older reader-generation report remains historical provenance for the metadata-only role.

Terraform validation and mocked boundary tests check the action exception, region condition, exact existing metadata scopes, explicit action ceiling and non-root trust guard. CI has no AWS credentials and cannot deploy. A private live review must verify identity, current role policies, exact planned changes, allowed/denied permission behavior, state routing and cost before requesting approval. Raw live audits and binary plans must remain private.
