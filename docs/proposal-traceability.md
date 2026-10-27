# Proposal requirements traceability

## Source and provenance
Final proposal: M_Morales_DIS997_Research_Proposal_FINAL_v2.docx, title “AI-Driven Adaptive Security Compliance Monitoring for AWS Cloud-Native Systems”, dated September 7, 2026.
SHA-256: `99ad4b0aa5e1af82346f5e8b0bb1e8388b48726dc8815b8f68bddf3df896f5db`.
Read successfully from the user-supplied OneDrive path on October 26, 2026. The source was not edited or published to the public repository.

Locations below are section numbers and reproducible OOXML paragraph indices (`P` counts every w:p in word/document.xml, including table paragraphs). They are not printed page numbers. Word pagination is not assumed from the table of contents.

## Requirements

| ID | Proposal section | Extracted paragraphs | Requirement | Implementation consequence |
|---|---|---|---|---|
| M01 | 3.2.2; 3.3.2 | P0708–P0725 | Matched scenario instance is experimental unit; retain scenario, repetition, variant and batch; equivalent inputs to both monitors. | Pairing and manifest validation; no independent-row analysis. |
| M02 | 3.3.3 | P0730–P0731 | External authoritative scenario sources; approximately half rule-matched and half combinatorial/drift; compliant/noncompliant balance; no selection on expected AI success. | Candidate catalog and independent AWS-security reviewer; balances checked before freeze. |
| M03 | 3.3.3; 3.6.4 | P0731; P0828–P0831 | Catalog version-lock and cryptographic hash before pilot; independent review before confirmatory; pilot instrument validation excluded from final tests. | Separate catalog freeze from confirmatory readiness; revisions create new catalog versions and repeated affected pilots. |
| M04 | 3.3.4 | P0734–P0738 | Simulation power >=.80; familywise alpha .05; Holm across five outcomes; planning binary OR 1.50; >=1,000 datasets per candidate design. | R power simulation must preserve pairing and scenario clustering; retain seeds, failures and all assumptions. |
| M05 | 3.3.4.1 | P0740–P0742 | Separate RMST power verification at 1,800s; planning censoring 15%; important difference 120s; sensitivity censoring 5–30% and difference 60–180s. | Final design is larger binary/RMST requirement; [N] is unresolved, not an achieved power result. |
| M06 | 3.4.1; 3.5.3; 3.6.2 | P0747–P0748; P0793–P0797; P0813–P0818 | Isolation Forest; bounded adaptation; deterministic automatic mapping uses threshold and corroborating predicates; retain all component versions; no runtime human classification. | Model thresholds, features, hyperparameters and exact bounds remain implementation decisions to specify and freeze. |
| M07 | 3.5; 3.5.1 | P0772–P0782 | Terraform; EC2, S3, Lambda, EKS, VPC, IAM; isolated from production and personal/customer data. | Stage resources; EKS is in final design, but no EKS or other paid deployment is approved now. |
| M08 | 3.5.2; 3.6.1 | P0784–P0790; P0807–P0810 | Config plus Security Hub CSPM primary baseline; applicable controls fixed and validated; CloudTrail timing; Audit Manager/conformance packs optional; GuardDuty outside baseline. | Inventory existing services first; no wholesale defaults or intentionally weakened baseline. |
| M09 | 3.7.2; 3.7.2.1 | P0848–P0860 | Automatic scenario injection and collectors; verified observable trigger; no researcher sees results during active window; randomized/counterbalanced order; restore state between scenarios. | Controller must hide live comparative results and retain schedule seed; recovery checked before each instance. |
| M10 | 3.7.3 | P0862–P0868 | Ground truth stored separately from predictions; pseudonymous resource ID; model, feature, mapping and adaptation provenance. | Join labels only after monitor outputs persist; raw evidence retained outside Git. |
| M11 | 3.7.4 | P0870–P0874 | Only predefined technical/procedural failures invalidate trials; poor outcomes never excluded; WARNING/NOT_AVAILABLE distinguish instrumentation failure from normal absence. | Retain exclusions and causes; unknown results must not silently become compliant. |
| M12 | 3.7.5 | P0876–P0880 | Separate training, validation/adaptation and held-out; account for related variants; current observations cannot update before scoring. | Use phase plus learning-role metadata; pilot never confirmatory; group-aware partition manifest. |
| M13 | 3.7.6 | P0882–P0886 | Common 1,800s window; first valid attributable detection; undetected violations right-censored at horizon and represented in FN analysis. | Distinguish censoring duration from a detected event; verify clock/ingestion timestamps. |
| M14 | 3.8.3–3.8.4 | P0905–P0935 | Four binomial logit GLMMs with approach fixed effect and scenario random intercept; paired/repeated clustering; RMST latency; OR, 95% CI, Holm p-values. | R locked environment; prespecify additional clustering supported by final design and diagnostics alternatives. |
| M15 | 3.8.4.2; 3.8.4.3; 3.8.4.4 | P0920–P0930 | FPR uses compliant; FNR uses noncompliant; coverage retains applicable scenarios without detection capability. | Finalize unknown-compliant denominator and baseline fusion policy before implementation freeze; do not drop uncovered scenarios. |

## Decisions the proposal leaves to implementation

- Exact feature schema, Isolation Forest hyperparameters/seed, anomaly-score orientation and calibrated threshold.
- Exact adaptation batch schedule, eligible completed observations, update bounds, contamination protections, rollback and model versioning.
- Executable evidence predicates and mapping outcomes for each scenario; freeze before data collection, with no ground-truth labels as detector inputs.
- Exact scenario count, balance tolerance, repetitions, family grouping, workload variations, reviewers and randomized schedule.
- Config/Security Hub result fusion, first valid classification versus final status, stale findings, and source/event/collection timestamp semantics.
- Treatment of an uncovered compliant instance in accuracy and FPR. Sections 3.4.3 and 3.8.4.2 give binary confusion-matrix formulas, while coverage explicitly retains unknown results. Noncompliant non-detections are explicitly FN; compliant unknowns are not explicitly defined as TN or FP. Preserve unknown separately until this choice is prespecified; never silently drop or relabel it.
- R package versions, precise paired/clustering implementation for RMST, simulation distributions, convergence/failure accounting and any diagnostic fallback.

These are open implementation specifications, not permission to alter the approved questions or infer outcomes. The [N] placeholder in section 3.3.4.1 cannot be reported as a computed sample size.

## Current completion boundary
Source intake and protocol constants are verified. Full catalog, independent review, instrument validation, power analysis and confirmatory readiness remain incomplete. No pilot or confirmatory research data have been collected.
