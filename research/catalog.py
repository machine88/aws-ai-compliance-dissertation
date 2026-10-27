"""Validate scenario designs and group-aware partitions without contacting AWS."""
import hashlib
import json
import random
from collections import Counter
from pathlib import Path
from research.contracts import FACTS, PROPOSAL_SHA256, WINDOW_SECONDS

ROLES = ("training", "validation_adaptation", "held_out")
SERVICES = {"S3", "EC2", "Lambda", "EKS", "VPC", "IAM"}
STRATA = {"rule_matched", "combinatorial_drift"}
LABELS = {"compliant", "noncompliant"}


def canonical_sha256(value):
    """Hash JSON content independently of whitespace and dictionary key order."""
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(raw.encode()).hexdigest()


def validate_catalog(catalog, truth):
    """Reject ambiguous labels, unmatched IDs, mixed families and imbalanced designs."""
    if catalog["proposal_sha256"] != PROPOSAL_SHA256 or catalog["observation_window_seconds"] != WINDOW_SECONDS:
        raise ValueError("catalog must match the final proposal and 1800-second window")
    rows = catalog["scenarios"]
    ids = [row["scenario_id"] for row in rows]
    labels = truth["entries"]
    if not ids or len(set(ids)) != len(ids) or set(ids) != set(labels):
        raise ValueError("scenario IDs must be unique and match separate ground truth")
    if catalog["version"] != truth["catalog_version"]:
        raise ValueError("ground truth belongs to another catalog version")
    if catalog["proposal_sha256"] != truth["proposal_sha256"]:
        raise ValueError("proposal provenance mismatch")
    families = {}
    for row in rows:
        if row["service"] not in SERVICES or row["stratum"] not in STRATA:
            raise ValueError("unknown service or stratum")
        if {"expected", "label", "ground_truth"} & row.keys():
            raise ValueError("labels must be stored separately from scenario metadata")
        if not row["sources"] or not row["control_ids"] or not row["family_id"]:
            raise ValueError("source, controls and family are required")
        signature = (row["service"], row["stratum"], row["leakage_group_id"])
        prior = families.setdefault(row["family_id"], signature)
        if prior != signature:
            raise ValueError("a related family cannot cross service or stratum")
        entry = labels[row["scenario_id"]]
        if entry["expected"] not in LABELS or not entry["required_facts"]:
            raise ValueError("independently specified ground truth is required")
        if set(entry["required_facts"]) - FACTS:
            raise ValueError("unsupported ground-truth technical fact")
        if any(type(value) is not bool for value in entry["required_facts"].values()):
            raise ValueError("draft ground-truth facts must be explicit booleans")
    cells = Counter((row["stratum"], labels[row["scenario_id"]]["expected"]) for row in rows)
    if set(cells) != {(s, label) for s in STRATA for label in LABELS} or len(set(cells.values())) != 1:
        raise ValueError("this design requires equal stratum-by-label cell counts")
    return {"scenarios": len(rows), "families": len(families),
            "services": sorted({row["service"] for row in rows}),
            "cell_counts": {f"{s}/{label}": cells[s, label] for s in sorted(STRATA) for label in sorted(LABELS)}}


def assign_learning_roles(catalog, seed):
    """Assign entire overlap groups before use without splitting related scenarios."""
    if type(seed) is not int:
        raise ValueError("retain an integer partition seed")
    groups = sorted({row["leakage_group_id"] for row in catalog["scenarios"]})
    if len(groups) < len(ROLES):
        raise ValueError("need at least three independent leakage groups; do not split related variants")
    random.Random(seed).shuffle(groups)
    group_roles = {group: ROLES[index % len(ROLES)] for index, group in enumerate(groups)}
    entries = [{"scenario_id": row["scenario_id"], "family_id": row["family_id"], "leakage_group_id": row["leakage_group_id"],
                "learning_role": group_roles[row["leakage_group_id"]]} for row in catalog["scenarios"]]
    manifest = {"catalog_sha256": canonical_sha256(catalog), "seed": seed,
                "algorithm": "seeded_leakage_group_round_robin_v1", "entries": entries}
    validate_assignments(catalog, manifest)
    return manifest


def validate_assignments(catalog, manifest):
    """Detect missing, duplicated or changed assignments and family leakage."""
    if manifest["catalog_sha256"] != canonical_sha256(catalog):
        raise ValueError("partition manifest does not match the catalog")
    definitions = {row["scenario_id"]: row for row in catalog["scenarios"]}
    rows = manifest["entries"]
    if len(rows) != len(definitions) or {row["scenario_id"] for row in rows} != set(definitions):
        raise ValueError("each scenario needs exactly one assignment")
    seen = {}
    for row in rows:
        if row["learning_role"] not in ROLES:
            raise ValueError("invalid learning role")
        if row["family_id"] != definitions[row["scenario_id"]]["family_id"]:
            raise ValueError("family metadata was changed")
        if row["leakage_group_id"] != definitions[row["scenario_id"]]["leakage_group_id"]:
            raise ValueError("leakage-group metadata was changed")
        roles = seen.setdefault(row["leakage_group_id"], set())
        roles.add(row["learning_role"])
        if len(roles) != 1:
            raise ValueError("related variants leak across learning partitions")


def readiness_errors(catalog):
    """Keep draft slices and unresolved assessment mappings out of formal runs."""
    errors = []
    if catalog["status"] != "ready_to_freeze":
        errors.append("catalog is still a draft")
    missing = SERVICES - {row["service"] for row in catalog["scenarios"]}
    if missing:
        errors.append("proposal service coverage incomplete: " + ", ".join(sorted(missing)))
    if any(row["nist_assessment_status"] != "verified" or row["stratum_review_status"] != "verified" for row in catalog["scenarios"]):
        errors.append("assessment mappings or scenario strata still need verification")
    return errors


def freeze_bundle(destination, catalog, truth, assignments):
    """Write one immutable full-catalog bundle only after structural readiness."""
    validate_catalog(catalog, truth)
    validate_assignments(catalog, assignments)
    errors = readiness_errors(catalog)
    if truth["status"] != "verified_technical_specification":
        errors.append("ground-truth technical specification is not verified")
    if errors:
        raise ValueError("; ".join(errors))
    bundle = {"catalog": catalog, "ground_truth": truth, "assignments": assignments}
    envelope = {"bundle_sha256": canonical_sha256(bundle), "bundle": bundle}
    with Path(destination).open("x") as stream:
        json.dump(envelope, stream, indent=2, sort_keys=True, allow_nan=False)
    return envelope["bundle_sha256"]
