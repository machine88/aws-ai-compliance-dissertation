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
