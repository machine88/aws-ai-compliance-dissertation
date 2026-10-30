# AWS AI Compliance Dissertation

The final proposal defines this study's methodology. The protected AWS foundation is deployed, and the approved CloudTrail-only development stage is logging. Config recording remains paused and Security Hub CSPM has no enabled standards. No pilot or confirmatory results exist.

Start with the [implementation plan](docs/implementation-plan.md), [proposal requirements](docs/proposal-traceability.md), [read-only inventory procedure](docs/aws-inventory.md) and [Phase 2 deployment review](docs/phase2-deployment-review.md).

## Current software

- Separate Terraform roots for protected state, bounded deployment access, a regional monitoring baseline and read-only evidence access. Source activation defaults remain false; the private approved configuration requests CloudTrail only. Later live plans must preserve that explicit configuration rather than accidentally request a pause.
- A disabled-by-default [dedicated development sandbox scaffold](docs/scenario-sandbox-review.md), with private versioned storage and a proposed trigger/restoration workflow. The [dedicated bounded deployment role](docs/sandbox-access-review.md) is approved, deployed and verified; bucket deployment and separate mutation approval remain pending.
- Two initial S3 instrument-control candidates and an explicit regional FSBP control snapshot. The independent, balanced scenario catalog is still pending.
- Encrypted development snapshot/history collectors, a fixed-horizon native scheduler, independent journal/source verification and a local Keychain-backed decryption helper. The approved one-shot native development capture verified three snapshots with no failed/skipped samples and a passing acquisition schedule. Captures remain development evidence, not research trials. Trigger validity, delivery completeness, source freshness and paired monitoring remain unvalidated.
- Offline Isolation Forest, bounded adaptation and deterministic mapping, with score-before-adapt and held-out protections. No study model has been trained; the draft catalog cannot yet support the required independent learning splits.
- Exact, assumption-based cost calculations and a deployed $100 monthly alert budget. Alerts do not cap spending; delivery of alert email has not been demonstrated.
- Local and CI validation using mocked providers, with no AWS credentials or deployment permissions in CI.

See the [current architecture and next instrument review](docs/prospective-instrument-review.md) for the remaining work and the distinction between logging enabled, delivery verified and research ready. Raw deployment/capture audits remain private.

## Offline checks

CI uses Terraform 1.15.0 and the checked-in provider lockfiles.

```sh
python3 scripts/check_function_docs.py
python3 -m unittest discover -s tests -v
python3 scripts/estimate_baseline_cost.py
terraform fmt -check -recursive infra
terraform -chdir=infra/bootstrap init -backend=false -input=false
terraform -chdir=infra/bootstrap validate
terraform -chdir=infra/bootstrap test
terraform -chdir=infra/baseline init -backend=false -input=false
terraform -chdir=infra/baseline validate
terraform -chdir=infra/baseline test
```

The legacy CLI preflight is read-only and rejects root/wrong-account sessions. Prefer AWS MCP for live inventory. Keep budget recipients, state, saved plans and raw account evidence outside Git. The final source proposal is not published here.

There is no automatic deployment workflow. Merging code does not approve AWS deployment. Review real saved plans, least-privilege permissions, costs, state recovery and teardown, then obtain explicit user approval as documented in the deployment review.
