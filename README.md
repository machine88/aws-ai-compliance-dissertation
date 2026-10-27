# AWS AI Compliance Dissertation

The final proposal defines this study's methodology. No research infrastructure has been deployed and no pilot or confirmatory results exist.

Start with the [implementation plan](docs/implementation-plan.md), [proposal requirements](docs/proposal-traceability.md), [read-only inventory procedure](docs/aws-inventory.md) and [Phase 2 deployment review](docs/phase2-deployment-review.md).

## Current software

- Separate Terraform roots for protected state storage and a regional Config, Security Hub CSPM and CloudTrail baseline. Collection defaults to paused; this is not an operational deployment.
- Two initial S3 instrument-control candidates and an explicit regional FSBP control snapshot. The independent, balanced scenario catalog is still pending.
- Evidence envelopes separating development, pilot and confirmatory records. Related learning-role separation remains to be implemented before model development.
- Exact, assumption-based cost calculations using a retained public pricing snapshot; no actual billing data or budget changes.
- Local and CI validation using mocked providers, with no AWS credentials or deployment permissions in CI.

## Offline checks

Use Terraform 1.14.3 (or a compatible supported version) and the checked-in provider lockfiles.

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
