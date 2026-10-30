# Sandbox administrative metadata checks

The approved empty-bucket saved plan was applied under the dedicated role: six S3 resources and one Terraform guard created, with zero updates or deletes. The post-apply Terraform plan reported no changes. Retained metadata confirmed Ohio location, exact development tags, four public-access blocks, owner-enforced ownership, Enabled versioning, SSE-S3 with SSE-C blocked, a TLS-deny-only policy and an empty complete current-object listing. No object was uploaded or read. Raw responses, the original checker failure and corrected verification remain private.

## API-shape correction

The first private check expected a flat SSE-C list and stopped. AWS's response uses `ServerSideEncryptionConfiguration.Rules[0].BlockedEncryptionTypes.EncryptionType`. The installed SDK service model and [GetBucketEncryption response schema](https://docs.aws.amazon.com/AmazonS3/latest/API/API_GetBucketEncryption.html) confirmed that structure. The corrected predicate was tested and applied to the already-retained responses; this correction required no new AWS calls, permission change or bucket mutation. The initial failure was retained rather than rewritten as a successful attempt.

`research/sandbox_readiness.py` now implements `verify_sandbox_metadata(responses, bucket)` as a pure administrative predicate. It accepts the exact nine-operation SDK-response map for the fixed sandbox. It checks required values explicitly, rejects duplicate policy JSON keys, extra policy grants, missing/malformed protection evidence and partial/nonempty current-object listings. Inputs are not modified; no clients, writes, credentials, source clocks or expected-answer labels are created. Synthetic tests exercise the AWS nested-container regression and the fail-closed boundaries.

## What the result establishes

The result describes supplied technical metadata. The caller must independently establish request scope, expected owner, actual source/role identity, timestamps and provenance. The function cannot authenticate its input or prove source freshness. These gates stay false in its result, even when a trusted caller has separately checked identity.

A complete empty current-object listing does not prove that noncurrent versions, delete markers and multipart uploads are absent. That distinct readiness flag remains false. The future scenario driver must perform the broader approved empty-state verification before any mutation. The predicate requires the deployed Enabled baseline and is suitable for proposed pre-state/restoration checks; it is not a detector for a live suspended-versioning interval.

No trigger, restoration loop, reader/injector permission expansion, feature release, ML fitting/adaptation, pilot or confirmatory run is authorized by these checks. Existing collector bucket allowlists are unchanged. Separate executable workflow, policy review, bounded live-run approval, instrument validation and the proposal's scientific gates remain required.
