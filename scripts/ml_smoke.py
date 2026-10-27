"""Exercise real ML code with synthetic development fixtures, never AWS study evidence."""
import argparse
import json
import random
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from research.contracts import FACTS
from research.ml import AdaptiveIsolationMonitor
from research.trials import write_prediction


def synthetic_rows(count, role, batch, seed, prefix):
    """Generate unlabeled fake telemetry solely for offline integration checks."""
    rng = random.Random(seed)
    return [{"sample_id": f"{prefix}-{index:03}", "phase": "development", "learning_role": role,
             "leakage_group_id": "group-" + role, "batch_id": batch, "completed": True,
             "features": {"mutation_count": rng.randint(20, 50), "policy_change_count": rng.randint(0, 4),
                          "public_access_change_count": rng.randint(0, 3), "versioning_change_count": rng.randint(0, 2),
                          "principal_count": rng.randint(1, 4), "configuration_delta_count": rng.randint(0, 5),
                          "failed_request_fraction": rng.uniform(0, 0.05)},
             "observed_facts": {name: True for name in FACTS}} for index in range(count)]


def persist_ai(root, model, row, prediction):
    """Write an AI determination before a validation observation may enter adaptation."""
    provenance = {key: prediction[key] for key in ("model_version", "feature_version", "mapping_version", "adaptation_version", "observation_sha256")}
    provenance["scenario_id"] = "SYNTHETIC-SMOKE"
    return write_prediction(root, "development", row["learning_role"], row["sample_id"],
                            row["leakage_group_id"], "ai", prediction["outcome"], provenance, model.protocol_sha256)


def run_smoke(destination):
    """Fit, score, persist, adapt and export models without estimating research accuracy."""
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    model = AdaptiveIsolationMonitor().fit(synthetic_rows(64, "training", 0, 997, "train"),
                                          synthetic_rows(32, "validation_adaptation", 1, 998, "anchor"))
    model.save_artifact(destination / "model-initial")
    adaptation = synthetic_rows(8, "validation_adaptation", 3, 999, "adapt")
    receipts = {}
    for row in adaptation:
        receipts[row["sample_id"]] = persist_ai(destination / "predictions", model, row, model.predict(row, "S3.5"))
    previous = model.version
    model.adapt(adaptation, next_batch=4, receipts=receipts)
    model.save_artifact(destination / "model-adapted")
    probe = synthetic_rows(1, "held_out", 4, 1000, "probe")[0]
    for name in probe["features"]:
        probe["features"][name] = 0.9 if name == "failed_request_fraction" else 50_000
    probe["observed_facts"]["end.tls_deny_present"] = False
    prediction = model.predict(probe, "S3.5")
    persist_ai(destination / "predictions", model, probe, prediction)
    summary = {"synthetic_only": True, "aws_calls": 0, "research_trials": 0,
               "algorithm": "IsolationForest", "protocol_sha256": model.protocol_sha256,
               "initial_model_version": previous, "adapted_model_version": model.version,
               "accepted_adaptation_updates": len([x for x in model.history if x["accepted"]]),
               "probe": prediction, "warning": "Engineering smoke test, not a dissertation performance result."}
    (destination / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    return summary


def main():
    """Create a new synthetic-only artifact directory and print its smoke-test summary."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, help="New directory; existing evidence is never overwritten")
    arguments = parser.parse_args()
    print(json.dumps(run_smoke(arguments.output), indent=2))


if __name__ == "__main__":
    main()
