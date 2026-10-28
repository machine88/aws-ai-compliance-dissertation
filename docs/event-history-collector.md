# Bounded development event-history inspection

The proposed command is `scripts/collect_event_history.py`. It performs a bounded inspection of already available CloudTrail management-event history after an interval has closed. This is not a real-time event-availability instrument or evidence of delivery completeness. The code has only been tested offline with SDK stubs. No live history queries, monitoring activation, IAM grants, recipient-key creation or research trials accompany this change.

It uses the fixed S3 mutation definitions from merged PR #16. Numeric extraction is available offline; live collection and delivery validation remain unapproved.

## Scope and privacy

The CLI accepts one reviewed bucket and an explicit, closed 1,800-second interval in the last 90 days. Plan mode outputs five EventName-filtered requests without opening an SDK session. No arbitrary operation names, regions, account selectors or endpoints are accepted. An execution additionally needs the reviewed-read opt-in, an authorized reader profile, a public recipient certificate and a new output directory. Existing encrypted-archive protections and reader account/role/location/project-tag guards apply.

CloudTrail LookupEvents supports only one lookup attribute, so EventName cannot be combined with a bucket filter. The five queries can return other buckets' events in the same account/region. Raw SDK-returned bounded pages are immediately encrypted before projection. Never publish or log these bodies. The inner serialized event and wrapper event ID/name are checked for consistency; account, region, S3 source, exact bucket and source interval are rechecked. Explicitly unrelated items are counted separately from malformed/unattributable items. The latter make decoding incomplete. This is application-level scope, not IAM bucket isolation.

The existing reader role does **not** permit LookupEvents: its boundary explicitly denies actions outside the current metadata-read set. A separate reviewed permission change and collection authorization are required before execution. This PR does not widen that role, switch to the provisioning identity to evade it, or create a new profile. Do not attempt denied queries against the deployed role merely to collect error logs.

## Bounded requests and status

The SDK paginator handles continuation tokens. A per-query item cap defaults to 1,000 and cannot exceed it: at most 5,000 returned items across five lookups before local filtering. PageSize is 50. A remaining SDK resume token is retained privately and marks pages_complete=false. SDK item capping can slice a returned page before application code sees it; the encrypted record is the bounded SDK-visible page, not an assertion of retaining the entire underlying HTTP response. Access errors retain explicit encrypted instrumentation-error records and never become empty successes.

A process-local before-send hook spaces each HTTP attempt, including retries, by at least 0.55 seconds. This does not coordinate other clients using the shared account/region quota. Standard retries have three total attempts, short connection/read timeouts and no arbitrary endpoint overrides. External traffic can still cause throttling, which remains an incomplete capture. See [LookupEvents API](https://docs.aws.amazon.com/awscloudtrail/latest/APIReference/API_LookupEvents.html) for the single-filter, page, history and quota constraints.

Every scoped event carries the actual page receipt time. Provider event time is never substituted for that clock. A historical lookup after the scoring cutoff cannot establish when an AI system could first have used an event. The feature extractor therefore cannot credit such a late receipt retrospectively.

The completion record keeps three separate properties:

| Field | Meaning |
| --- | --- |
| pages_complete | All five bounded SDK queries returned without API failure or truncation. |
| decoding_complete | No malformed/unattributable event was found in the returned pages. |
| delivery_verified | Always false: successful lookup pagination is not proof that CloudTrail has delivered all relevant events. |
| primary_trial_ready | Always false: this retrospective inspection cannot establish prospective detection latency or a valid experiment. |

Exit zero means only successful bounded inspection. It does not override the false delivery/trial flags. Errors can leave a partial archive without a terminal completion marker; preserve it for diagnosis and never use it as complete data.

## What this unlocks and what it does not

This gives us a tested encrypted mechanism for inspecting available history and checking S3 event formats during a future approved development session. It does not activate the paused trail or recorder, prove loss-free capture, provide scheduled point-in-time snapshots, join ground truth, train a model or create pilot/confirmatory evidence.

Prospective collection, independent trigger/control-event delivery checks, feasible snapshot timing, trusted encrypted-archive ingestion and an audited model/controller binding still need implementation and validation. The strict synthetic endpoint rules in the feature extractor also need live feasibility review. Those gaps must be resolved before using extracted vectors to claim dissertation results.

Offline validation uses real SDK parameter/paginator models, dummy credentials and stubbed responses: wrong identity, multiple pages, item cap, denied queries, malformed data, returned-resource attribution and request pacing. No AWS endpoint is contacted by these tests.
