# State migration review: pending approval

PR #4 is merged and its exact approved access plan was applied: three managed policies, one bounded deployment role, two attachments, and a local Terraform identity guard. The role session was verified using Terraform without printing credentials. Its post-deployment plan reports no changes.

The next proposed action moves the two existing local state files into the already-created state bucket. This does not deploy the monitoring baseline or enable collection. Approval is required before any remote state write.

## Scope and isolation

Use existing bucket `dissertation-653464153304-us-east-2-state`, region `us-east-2`, and the non-root `dissertation` provisioning profile. The provisioning identity manages only these administrative state migrations; the restricted baseline role intentionally cannot access either key.

| Root | Destination key |
| --- | --- |
| bootstrap | `dissertation/653464153304/us-east-2/bootstrap/terraform.tfstate` |
| access | `dissertation/653464153304/us-east-2/access/terraform.tfstate` |

The baseline retains its separate `baseline/terraform.tfstate` key and uses the restricted role for future backend access. Every backend requires encryption, native S3 lockfiles and the expected account ID. Only the default workspace is supported; do not run concurrent Terraform operations.

## Execution and verification

1. Verify current caller identity is the expected non-root account identity. Retain mode-600 copies of both local state files, their SHA-256 hashes, lineage, serial, and all managed resource addresses and IDs. Do not print state contents.
2. Confirm destination keys are absent before migration. If an object already exists, stop and inspect its lineage instead of overwriting it.
3. Replace each root's local backend with an empty S3 backend block, using its reviewed backend example for the account, bucket, key, region, profile and locking settings. Commit that backend transition separately before execution. Backend-only changes do not authorize resource changes.
4. Migrate one root at a time using Terraform's state migration support. Do not use an unconditional force-copy option. Confirm the intended source and destination, then copy the existing state; keep the protected backups.
5. Pull each remote state privately and compare lineage, resource addresses and IDs against the backup. Record the serial and explain any change; require a no-change resource plan after migration. Confirm versioning, encryption, public access blocking and TLS-only bucket policy remain intact.
6. If verification fails, stop before any resource apply. Preserve both copies; do not delete remote objects, force-push state, or recreate resources. Review which backend contains the authoritative state before recovery.

S3 storage and request charges apply to state and lock objects. This proposal creates no additional buckets, compute, paid monitoring collection or research scenarios. The proposed monitoring budget has not yet been created and is an alert, not a spending cap. See the [S3 pricing page](https://aws.amazon.com/s3/pricing/) for storage and request rates; no zero-cost guarantee is made.

## Existing encryption protection

A read-only refresh found that the state bucket blocks SSE-C. The original Terraform configuration omitted this field and proposed removing the block. This change explicitly preserves `blocked_encryption_types = ["SSE-C"]` and the observed `bucket_key_enabled = false`, while retaining AES256 encryption. The future telemetry bucket uses the same explicit protection. No bucket update was applied. See [AWS blocked encryption types](https://docs.aws.amazon.com/help-panel/AmazonS3/latest/console/hp-bucket-properities-default-encryption-blocked-types.html).

After successful state migration, generate a fresh restricted-role monitoring plan for separate approval. The earlier local-backend preview is not an approved deployment artifact. Pilot and confirmatory data collection remain unstarted and separate.
