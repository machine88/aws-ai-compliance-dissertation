# Offline full-bucket emptiness contract

The deployed bucket has only an administratively verified empty current-object listing. Its older versions, delete markers and unfinished multipart uploads have not been checked live. `research/sandbox_emptiness.py` now validates supplied listing receipts for those additional boundaries without cloud access.

## Contract

`verify_empty_sandbox_listings(receipts, bucket)` requires exactly `list_objects_v2`, `list_object_versions` and `list_multipart_uploads` receipts. Each receipt contains `region`, `request` and `response`. The region is Ohio; every request names the dedicated sandbox and expected account owner, with an explicit 1000-entry ceiling and no other parameters. Prefix, delimiter, continuation and starting-marker request parameters are rejected, even if a caller believes the subset is harmless.

Responses must name the exact bucket, retain HTTP 200 metadata and explicitly report `IsTruncated=false`. Current-object `KeyCount` must be integer zero. Every returned Contents, Versions, DeleteMarkers, Uploads or CommonPrefixes collection applicable to that operation must be an empty list; omitted empty collections are accepted because parsed SDK responses may omit them. Null or malformed collections fail. Nonempty filters/markers, error payloads, inconsistent page ceilings and partial results fail. An actually empty full bucket fits a single page; pagination is deliberately not used to repair an apparent empty result.

The response names, collection names and pagination fields follow AWS's [ListObjectsV2](https://docs.aws.amazon.com/AmazonS3/latest/API/API_ListObjectsV2.html), [ListObjectVersions](https://docs.aws.amazon.com/boto3/latest/reference/services/s3/client/list_object_versions.html) and [ListMultipartUploads](https://docs.aws.amazon.com/boto3/latest/reference/services/s3/client/list_multipart_uploads.html) contracts. The local predicate is stricter than the APIs because it checks only the proposed empty-bucket precondition, not general-purpose listings.

## Meaning and limits

The result establishes consistency of caller-supplied empty responses and request scope. It does not authenticate receipts, establish actual request/receipt clocks, prove owner or role identity, prevent concurrent writers, or certify atomic emptiness across three separate requests. Source identity, freshness, concurrency exclusion, mutation authorization, trigger and ML gates stay false. A future runner must bind retained encrypted receipts to actual scoped calls, deadlines and independent identity checks, and enforce an execution lock and writer exclusion. The existing administrative metadata predicate remains unchanged and must also pass before a future suspension.

This is not a collector, live preflight, permission expansion or scientific instrument. No deployed allowlists changed. No object body reads, deletions, upload abortions, mutations or captures are performed or authorized. Local tests use synthetic fixtures; zero research trials are created. A future reviewed live check would incur S3 request charges, with retries and call caps included in its cost estimate. No new paid monitoring is enabled by this code.

## Next integration boundary

Combine this predicate with the existing protection checks and recovery planner in a tested, encrypted, locked driver only after specifying identity separation, credential lifetime, receipt clocks, deadline budget and manual recovery. Do not translate a returned `supplied_listings_empty=true` into the recovery planner's `preflight_retained` event on its own. Explicit approval of a bounded live plan remains necessary.

`verify_sandbox_prestate(metadata, receipts)` is the offline composition boundary: it requires both the existing nine-operation protection check and the three listing receipts. It returns both reports intact and `live_execution_allowed=false`. It never emits the recovery planner's preflight event. Synthetic integration tests reject either Suspended pre-state or residual delete markers even when the companion report passes.
