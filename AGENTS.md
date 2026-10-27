# Dissertation project safeguards

- Use AWS profile `dissertation`, expected account `653464153304`, default research region `us-east-2`.
- Verify identity before AWS work. Do not use root sessions.
- Do not deploy or incur research infrastructure charges without explicit user approval of a reviewed plan.
- Use version-controlled Terraform for this study. Preserve existing account resources and isolate state.
- The final dissertation proposal is the methodological source of truth; do not substitute chat summaries.
- Keep development, pilot and confirmatory evidence separate. Do not invent research results.

## Code documentation

- Give every function and method a brief description of what it does, including test helpers and test methods. Use Python docstrings and the equivalent concise comment style in other languages.
- Add short file or module descriptions and comments for configuration blocks or non-obvious code where they help explain purpose, safeguards or research assumptions.
- Keep comments plain and concise. Explain intent without narrating obvious operations; update descriptions whenever behavior changes.
- Apply this convention to both new code and existing code touched during implementation.

<!-- BEGIN AWS Agent Toolkit rules -->
# AWS Guidance

- Where these AWS rules conflict with the project's own instructions, the
  project's instructions take precedence.
- Prefer the AWS MCP Server for AWS interactions — it provides sandboxed
  execution, observability, and audit logging. If unavailable, use the
  AWS CLI directly.
- Before starting a task, check whether a relevant AWS skill is available.
  Load the skill with `retrieve_skill` and prefer its guidance over
  general knowledge.
- When uncertain about specific AWS details (API parameters, permissions,
  limits, error codes), verify against documentation rather than guessing.
  State uncertainty explicitly if you cannot confirm.
- When creating infrastructure, prefer infrastructure-as-code (AWS CDK or
  CloudFormation) over direct CLI commands.
- When working with infrastructure, follow AWS Well-Architected Framework
  principles.
- Do not use em dashes in AWS resource names or descriptions. Use
  hyphens instead.

## Secret Safety

- MUST load the `aws-secrets-manager` skill first for any secret,
  credential, API key, token, or password task. MUST NOT call
  `secretsmanager get-secret-value` or `batch-get-secret-value`, and MUST
  NOT hit the Secrets Manager Agent daemon directly. MUST use
  `{{resolve:secretsmanager:secret-id:SecretString:json-key}}` with
  `asm-exec` so the secret resolves at runtime without entering context.
<!-- END AWS Agent Toolkit rules -->
