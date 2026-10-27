"""Demonstrate paired controller integration with explicitly synthetic design groups."""
import argparse
import copy
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from research.catalog import assign_learning_roles, canonical_sha256
from research.controller import DevelopmentController, evaluate_pair, write_private_json
from scripts.ml_smoke import synthetic_rows


def synthetic_design():
    """Construct artificial groups solely to test controller wiring, never study validity.

    Inputs:
        Repository draft S3 catalog and its separately authored expected-answer file.

    Outputs:
        tuple: Synthetic-marked catalog, expected answers and seeded role assignments.
    """
    root = Path(__file__).resolve().parents[1]
    catalog = json.loads((root / "protocol/scenarios/development-s3-v0.1.json").read_text())
    truth = json.loads((root / "protocol/ground-truth/development-s3-v0.1.json").read_text())
    catalog = copy.deepcopy(catalog)
    catalog["fixture_notice"] = "Artificial independence groups for engineering tests only; not a valid experimental design."
    # The real development catalog remains one overlapping group; never write this fixture back to it.
    for row in catalog["scenarios"]:
        row["leakage_group_id"] = "synthetic-group-" + str((int(row["family_id"][1:]) - 1) % 3)
    return catalog, truth, assign_learning_roles(catalog, seed=997)


def bound_fixtures(catalog, assignments, role, count, batch, prefix):
    """Make fake observations that match one explicitly assigned fixture scenario.

    Inputs:
        catalog: Synthetic-marked catalog used by the integration check.
        assignments: Its matching learning-role manifest.
        role: Training, validation/adaptation or held-out role to exercise.
        count: Number of synthetic observations to create.
        batch: Completed development batch number.
        prefix: Unique safe prefix for generated sample identifiers.

    Outputs:
        list[dict]: Label-free scenario envelopes with matching role/group metadata.
    """
    scenario = next(entry["scenario_id"] for entry in assignments["entries"] if entry["learning_role"] == role)
    definition = next(row for row in catalog["scenarios"] if row["scenario_id"] == scenario)
    rows = synthetic_rows(count, role, batch, 997 + batch, prefix)
    for row in rows:
        row["leakage_group_id"] = definition["leakage_group_id"]
    return [{"scenario_id": scenario, "observation": row} for row in rows]


def synthetic_baseline(envelope):
    """Supply an explicit unknown adapter result without pretending to call AWS.

    Inputs:
        envelope: Synthetic observation to which the fake adapter result must refer.

    Outputs:
        dict: Unknown baseline outcome, synthetic source version and exact observation hash.
    """
    return {"outcome": "unknown", "source_version": "synthetic-adapter-no-aws",
            "observation_sha256": canonical_sha256(envelope["observation"])}


def run_controller_smoke(destination):
    """Exercise paired persistence, bounded adaptation and delayed label joining offline.

    Inputs:
        destination: New private development-run directory.

    Outputs:
        dict: Synthetic-only run summary; writes paired decisions, model artifacts and one evaluation.
    """
    catalog, truth, assignments = synthetic_design()
    controller = DevelopmentController(destination, catalog, assignments, canonical_sha256(truth))
    controller.fit(bound_fixtures(catalog, assignments, "training", 64, 0, "fit"),
                   bound_fixtures(catalog, assignments, "validation_adaptation", 32, 1, "anchor"))
    # Both monitor outputs must be retained before any validation observation can update the model.
    validation = bound_fixtures(catalog, assignments, "validation_adaptation", 8, 3, "adapt")
    for envelope in validation:
        controller.run_pair(envelope, synthetic_baseline(envelope))
    controller.adapt(validation, next_batch=4)
    heldout = bound_fixtures(catalog, assignments, "held_out", 1, 4, "evaluate")[0]
    result = controller.run_pair(heldout, synthetic_baseline(heldout))
    # The expected-answer file reaches evaluation only after the held-out pair is committed.
    evaluate_pair(destination, "held_out", heldout["observation"]["sample_id"], catalog, truth, assignments)
    summary = {"synthetic_only": True, "aws_calls": 0, "research_trials": 0,
               "development_pairs": len(validation) + 1, "heldout_pair_state": result["pair_state"],
               "model_version": controller.monitor.version, "context": controller.context,
               "warning": "Artificial design groups and unknown baseline adapter; no study performance estimate."}
    write_private_json(Path(destination) / "summary.json", summary)
    return summary


def main():
    """Run the synthetic paired-controller demonstration in a new output directory.

    Inputs:
        CLI --output naming a new private directory for synthetic artifacts.

    Outputs:
        None: Prints a synthetic-only summary and retains the checked artifact files.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    arguments = parser.parse_args()
    print(json.dumps(run_controller_smoke(arguments.output), indent=2))


# Importing helpers has no execution effect; run the demo only as an explicit command.
if __name__ == "__main__":
    main()
