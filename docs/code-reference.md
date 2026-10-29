# Code explanations and interfaces

Every maintained Python function/method now has a concise purpose, named `Inputs:` descriptions and an `Outputs:` description covering its return and file/state effects. A function with no explicit arguments or no return value states that explicitly. Important validation, model, evidence and adaptation blocks also carry intent comments. Terraform declarations and examples explain their inputs and resulting objects; CI steps identify their inputs and outputs.

For example, `AdaptiveIsolationMonitor.predict` documents the observation and mapping target it accepts, the prediction dictionary it returns, and the fact that scoring does not refit the model. The code around it explains unseen-data checks, related-group protection, evidence identity and the anomaly/technical-evidence gate. The ML configuration comments explain each parameter and the units of its bound.

`scripts/check_function_docs.py` now checks for a purpose, nonempty Inputs/Outputs sections and a description for each positional, keyword-only or variable-length argument. It checks module purposes too. Three regression tests ensure that a one-line description or partially described interface cannot pass. These checks confirm structure; reviewers must still ensure the descriptions explain the behavior accurately.

## JSON configuration reference

JSON does not support comments. The following descriptions explain the existing documents without changing their schema, policy permissions or content hashes. These are data/configuration interfaces rather than callable functions.

| File | Purpose | Inputs represented | Output or consumer |
| --- | --- | --- | --- |
| `protocol/proposal-constraints.json` | Retain proposal requirements and unresolved methodological choices. | Final proposal fingerprint, outcomes, power assumptions, collection requirements. | Protocol/candidate-design review; its original deployment flag is not a current infrastructure inventory. |
| `protocol/baseline-price-snapshot.json` | Retain exact public Ohio unit rates and refresh provenance. | AWS Price List SKUs, units, publication dates and USD rates. | Decimal cost calculator and budget review; not a live bill or spend cap. |
| `protocol/scenarios/development-s3-v0.1.json` | Describe draft conditions without expected labels. | Source references, neutral IDs, family/overlap groups, provisional strata, control candidates and explicit technical mapping targets. | Catalog validation and readiness audit; cannot freeze this incomplete slice. |
| `protocol/ground-truth/development-s3-v0.1.json` | Store separately authored draft expected answers. | Matching scenario IDs, expected states and stated technical facts. | Offline evaluation after paired predictions persist; never model features. |
| `protocol/ml-development-v0.1.json` | Retain proposed model and adaptation settings. | Seed, forest size, feature order, threshold calibration, technical targets and bounded-update policy. | Engineering review and reproducible development runs; not a frozen formal-study protocol. |
| `infra/baseline/fsbp-controls-us-east-2.json` | Pin the reviewed regional control-ID snapshot. | Available control IDs and snapshot provenance. | Terraform's explicit standard/control configuration after separately approved activation. |
| `infra/access/generated-baseline-policy.json` | Preserve the plan-derived identity permissions. | IAM Policy Autopilot output for proposed baseline resources. | Deployment-role policy; its broad grants must remain constrained by the mandatory boundary. |
| `infra/access/deployment-boundary.json` | Limit the maximum authority of the deployment role. | Exact account, region, resource/state-key patterns and explicitly permitted actions. | Permissions boundary on the role from creation; never a standalone grant of access. |
| `infra/access/backend-and-read-policy.json` | Supply scoped state-backend and metadata-read permissions. | Exact baseline state/lock keys and provider read requirements. | Deployment-role policy, still limited by the boundary. |

Policy JSON files are not edited to insert fake comment properties, and formal artifact or catalog hashes are not changed to carry documentation. Raw observations, state, plans, model files and private budget details remain outside Git.

## Learning terms

- **Input:** the values or files a function/configuration reads.
- **Output:** its returned value and anything it writes or changes.
- **Validation:** checks that reject incomplete, unsafe or methodologically invalid inputs.
- **Provenance:** version/hash metadata explaining which inputs and implementation produced a result.
- **Side effect:** a file or state change beyond the function's returned value.

The scientific pipeline remains development-only and AWS collection remains paused. These explanation changes do not activate monitoring or alter research outcomes.

The offline controller adds a retained design record and pairs bound to catalog, assignment and predeclared answer-key hashes. See `development-controller.md` for each interface and its outputs. These private run files stay under ignored evidence storage.

`protocol/timing-development-v0.1.json` retains the proposed timing clock, fixed 1,800-second horizon, endpoint/censoring rules and unresolved review requirements. Inputs are the proposal constraints and explicit development clock policy; output is the reviewable timing specification used by `research/timing.py`. See `timing-and-censoring.md` for event/window interfaces and the separate post-persistence label join.

## Read-only development collector

`requirements-aws.txt` pins the SDK and temporary-login runtime. `research/aws_reader.py` defines the fixed read scope and encrypted archive. `scripts/collect_snapshot.py` accepts a reader profile, one approved bucket, a new output directory, a public certificate and an optional pagination bound. It outputs encrypted development observations and a count/status summary. `--plan` outputs requests only, without credentials or AWS calls. See `docs/read-only-collectors.md` for scope and limitations.

## Reader access review

`infra/reader/generated-reader-policy.json` is the unedited identity-policy portion of IAM Policy Autopilot output. Inputs are runtime SDK source plus the tested analysis expansion; the Terraform root applies a separate boundary before any grant. `protocol/reader-policy-generation.json` records tool version, source/expanded-input hashes, policy hash, warnings and uncompleted live checks. It contains no inventory, credentials or deployment approval. `scripts/export_reader_policy_input.py` writes analysis-only source without executing AWS calls. Required Config ARN variables have no guessed defaults. See `evidence-reader-review.md` for the state key, authority limits and approval gate.

## Snapshot observation adapter

`research/observations.py` accepts decoded development envelopes for one reviewed bucket and an explicit observation slot. It outputs partial technical booleans, separately scoped Config/CSPM statuses, source hashes and readiness limits. It does not decrypt archives, authenticate envelopes, infer absent ML counts, fuse monitor decisions or join expected answers. See `observation-adapter.md` for supported policy patterns, missing-data semantics and remaining integration work. Every function describes its inputs and outputs.

## Event feature extraction

`research/event_features.py` accepts decoded event envelopes, complete boolean state frames and an exact development coverage declaration. It outputs seven proposed model-compatible numeric fields only when scope, availability, snapshots and completeness pass; otherwise it returns no feature vector and explicit blockers. Its source hashes and extraction version must enter the future controller audit. It does not collect events, prove completeness, train a model or expose answers. See `event-feature-extraction.md` for definitions, strict synthetic endpoint limitations and remaining live integration work.

## Development event-history inspection

`research/event_history.py` creates fixed, closed-interval lookup plans, paces HTTP attempts and projects scoped event envelopes while retaining issue counts. `scripts/collect_event_history.py` accepts plan-only or explicitly authorized inspection arguments and writes encrypted SDK-visible pages/projections. Its completion record distinguishes pagination, decoding and unverified delivery; it never marks primary trial readiness. `event-history-collector.md` explains the account/region breadth, capture approval gate, limits and why historical receipts cannot establish detection latency. This code does not change the deployed reader policy.

## Proposed event-history permission

`protocol/history-reader-policy-generation.json` records reproducible source/expansion/policy hashes for the unapplied history-reader proposal. The existing identity-policy file remains unedited analyzer output; the Terraform boundary limits its new LookupEvents action to Ohio. The source exporter and parity test now include both snapshot and history plans. `history-access-proposal.md` explains the unavoidable regional history-read breadth and separate deployment/capture approval gates. No raw live audit or saved-plan metadata is published by these references.

## Private archive ingestion

`research/archive_ingestion.py` accepts an owned private capture directory, trusted authenticated-decryption callback, independently pinned public-certificate hash and expected reviewed bucket. It returns verified in-memory record chains and scoped normalization without writing plaintext. POSIX permissions/link checks, size limits, strict JSON and ciphertext receipts prevent silent corruption or source substitution; explicit false flags prevent claims of sender authentication, provider delivery or formal-trial readiness. Shared optional S3-absence codes now live in `research/aws_reader.py`. See `archive-ingestion.md` for the trusted boundary, source/projection checks and remaining production key integration.

## Local recipient preparation and request bounds

`scripts/macos_prepare_recipient.swift` accepts one new local output directory and prepares an encrypted recipient with a dedicated Keychain unlock secret; comments describe its helper's public arguments, sensitive in-memory stdin and output. It prints no secret values and has no AWS calls. Both collectors accept a separately bounded max-pages option alongside max-items, with explicit incomplete records at either limit. See `local-recipient-setup.md`; native setup, permission deployment and actual capture each retain their appropriate authorization boundaries.

## Local Keychain decryption boundary

`research/keychain_decryption.py` binds an independently fingerprinted private executable and recipient to a callable archive-decryption boundary. It returns authenticated bytes through captured pipes, keeps temporary files encrypted and reports generic failures without child output. `scripts/macos_decrypt_record.swift` retrieves only the dedicated local recipient secret and withholds plaintext until CMS authentication succeeds. It is a subprocess protocol, not a terminal display command. See `keychain-ingestion.md` for native authorization, trusted-host limits and offline test coverage.

## Independently staged monitoring

`infra/baseline/variables.tf` adds three off-by-default service requests alongside the legacy all-on switch. Locals resolve each component; planning guards reject mixed positive interfaces and CSPM without Config. The existing collection_enabled output reflects any requested component. `staged-activation.md` explains combinations, unchanged recording/logging scope, complete pause inputs and separate permission/deployment gates. The paused live plan remains unchanged; no activation accompanies this source change.

## CloudTrail-only permission proposal

`infra/access/deployment-boundary.json` proposes one additional named-trail StartLogging permission in its existing regional statement; the generated identity policy remains unchanged. The access regression test checks named-trail/region scope and continued absence of Config start. `trail-only-permission-proposal.md` explains the two-root saved-plan gate, unchanged telemetry selectors, persistent logging and separate capture/research permissions. Raw live reviews and assumed-volume cost calculations remain private.
## Development sampling audit

`research/sampling.py` validates a declared schedule against source-bound request receipts without AWS calls. `audit_sampling` retains acquisition clocks and blockers; timing success never enables ML or formal trials. `nonnegative_seconds` rejects implicit/invalid timing bounds. See [sampling-contract.md](sampling-contract.md) for exact schema meanings and the unchanged feature-integration boundary. Tests use synthetic clocks only.

## Verified sampling receipts

`research/capture_sampling.py` verifies independently pinned encrypted snapshots before projecting one exact non-paginated request into the sampling audit. `audit_snapshot_sampling` takes explicit plan/source/certificate/bucket/request inputs, returns hash-bound timing metadata and legacy blockers, and writes no plaintext. Future non-paginated snapshot responses and errors retain request-start and receipt clocks; paginated pages do not infer starts. See [verified-sampling-receipts.md](verified-sampling-receipts.md).

## Per-fact state frames

`research/state_frames.py` exposes `build_state_frame` for a pinned development snapshot and three exact configuration-record pins. It returns six boolean/unknown facts with separate provenance and acquisition intervals, explicit timing/unknown blockers, and false atomic/ML/formal-readiness flags. It does not supply an aggregate source observation time or change feature extraction. See [state-frames.md](state-frames.md).

## Adjacent frame comparison

`research/frame_comparison.py` exposes `compare_state_frames` for ordered pinned source archives and explicit acquisition/receipt-gap bounds. It rebuilds frames, rejects reuse/reordering, retains per-fact changed/unchanged/unresolved comparisons and withholds the candidate delta count if any local check fails. The existing extractor/model remain unchanged. See [frame-comparison.md](frame-comparison.md).

## Verified feature-component bundle

`research/feature_bundle.py` exposes `build_feature_bundle` for pinned history/snapshot sources and a source-locked development window. It retains seven candidate components, timing/readiness blockers and transitive source hashes, with no released model vector. `research/event_features.py` shares `count_event_inputs` between this audit and the unchanged strict extractor. See [feature-bundle.md](feature-bundle.md).
