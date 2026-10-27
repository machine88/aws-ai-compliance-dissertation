"""Export the proposed ML configuration for methodological review, without fitting data."""
import json
import sys
from dataclasses import asdict
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from research.ml import AdaptiveIsolationMonitor, FEATURES, FEATURE_VERSION, MAPPING_VERSION, TARGETS


def main():
    """Retain machine-readable development parameters; this does not freeze a protocol.

    Inputs:
        Default development ML configuration and versioned feature/mapping definitions.

    Outputs:
        None: Writes the unfrozen development ML specification JSON.
    """
    model = AdaptiveIsolationMonitor()
    # Export proposed parameters and known limitations without claiming a formally frozen study protocol.
    specification = {"status": "development_proposal_not_frozen", "algorithm": "IsolationForest",
        "parameters": asdict(model.config), "protocol_sha256": model.protocol_sha256,
        "feature_version": FEATURE_VERSION, "feature_order": FEATURES,
        "transformation": "log1p on six count features; unscaled failed-request fraction",
        "score_orientation": "negative sklearn score_samples; higher means more anomalous",
        "threshold": "higher empirical quantile of separate unlabeled validation anchor scores",
        "mapping_version": MAPPING_VERSION, "technical_targets": TARGETS,
        "adaptation_intake": "previous completed development validation batches with saved AI receipts and complete technically clean state",
        "normal_reference_guard": "all proposed start/middle/end technical predicates present and true; not independent ground truth",
        "limits": ["No AWS collector or real observations", "No pilot or confirmatory use",
                   "No held-out updates", "No ground-truth labels in model input",
                   "No claim that synthetic outputs estimate research performance",
                   "Catalog manifest/controller and scientific freeze integrations pending"]}
    destination = Path(__file__).resolve().parents[1] / "protocol/ml-development-v0.1.json"
    destination.write_text(json.dumps(specification, indent=2) + "\n")
    print("Development ML protocol exported; no fit, AWS call or formal freeze.")


if __name__ == "__main__":
    main()
