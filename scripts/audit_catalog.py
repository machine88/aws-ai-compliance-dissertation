"""Audit development scenario contracts; this command cannot freeze or run AWS trials."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from research.catalog import assign_learning_roles, readiness_errors, validate_catalog


def main():
    """Report balance, missing methodological gates and blocked family splits."""
    root = Path(__file__).resolve().parents[1]
    catalog = json.loads((root / "protocol/scenarios/development-s3-v0.1.json").read_text())
    truth = json.loads((root / "protocol/ground-truth/development-s3-v0.1.json").read_text())
    summary = validate_catalog(catalog, truth)
    summary["formal_readiness_errors"] = readiness_errors(catalog)
    try:
        summary["partitions"] = assign_learning_roles(catalog, seed=997)
    except ValueError as error:
        summary["partition_status"] = str(error)
    summary["aws_side_effects"] = False
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
