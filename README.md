# AWS AI Compliance Dissertation

Phase 1 local foundation. No AWS resources have been deployed and no empirical research results exist.

Read [implementation plan](docs/implementation-plan.md) and [proposal intake](docs/proposal-traceability.md).
The final proposal and authenticated target-account identity remain prerequisites.

Offline checks: `python3 -m unittest discover -s tests -v`
Read-only inventory after secure local login: `python3 scripts/preflight.py --profile RESEARCH_PROFILE --region REVIEWED_REGION`

`infra/baseline` is an account-guarded Terraform foundation, not a completed monitoring baseline. No apply workflow exists. Deployment requires explicit approval of the reviewed plan.

Evidence partitions are development, pilot and confirmatory. Offline test fixtures are software tests, not research observations. Keep raw evidence outside Git and preserve source timestamps and provenance; local exclusive writes prevent accidental overwrite but do not provide tamper-proof storage.
