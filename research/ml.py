"""Development-only Isolation Forest, evidence-gated mapping and bounded batch adaptation."""
import copy
import hashlib
import math
import os
import platform
import scipy
from dataclasses import asdict, dataclass
from pathlib import Path
import json
import joblib
import numpy as np
import sklearn
from sklearn.ensemble import IsolationForest
from research.catalog import canonical_sha256
from research.contracts import FACTS
from research.trials import safe_id

FEATURE_VERSION = "development-telemetry-v0.1"
MAPPING_VERSION = "development-evidence-gates-v0.1"
FEATURES = ("mutation_count", "policy_change_count", "public_access_change_count",
            "versioning_change_count", "principal_count", "configuration_delta_count",
            "failed_request_fraction")
TARGETS = {
    "S3.5": ("end.tls_deny_present",),
    "S3.8": tuple("end." + name for name in ("block_public_acls", "ignore_public_acls", "block_public_policy", "restrict_public_buckets")),
    "S3.14": ("end.versioning_enabled",),
    "S3_TLS_ACCESS": ("end.tls_deny_present",) + tuple("end." + name for name in ("block_public_acls", "ignore_public_acls", "block_public_policy", "restrict_public_buckets")),
    "S3_VERSIONING_WINDOW": tuple(f"{time}.versioning_enabled" for time in ("start", "middle", "end")),
    "S3_TLS_VERSIONING_WINDOW": tuple(f"{time}.{name}" for time in ("start", "middle", "end") for name in ("tls_deny_present", "versioning_enabled")),
}


@dataclass(frozen=True)
class MLConfig:
    """Proposed development bounds; these are not a frozen confirmatory protocol."""
    seed: int = 997
    trees: int = 128
    max_samples: int = 256
    min_training: int = 32
    min_calibration: int = 16
    calibration_quantile: float = 0.98
    max_training_rows: int = 512
    max_new_rows: int = 32
    max_new_fraction: float = 0.20
    max_updates: int = 4
    update_batches: tuple = (4, 6, 8, 10)
    max_threshold_step: float = 0.025
    max_threshold_total: float = 0.05
    max_anchor_score_shift: float = 0.15

    def __post_init__(self):
        """Reject configurations that remove sample, update or threshold bounds."""
        integers = (self.seed, self.trees, self.max_samples, self.min_training,
                    self.min_calibration, self.max_training_rows, self.max_new_rows, self.max_updates)
        if any(type(value) is not int or value < 1 for value in integers):
            raise ValueError("positive integer model and adaptation bounds required")
        fractions = (self.calibration_quantile, self.max_new_fraction,
                     self.max_threshold_step, self.max_threshold_total, self.max_anchor_score_shift)
        if any(not math.isfinite(value) or not 0 < value < 1 for value in fractions):
            raise ValueError("finite fractional bounds required")
        if self.max_training_rows < self.min_training or self.max_threshold_step > self.max_threshold_total:
            raise ValueError("inconsistent training or threshold bounds")
        if not isinstance(self.update_batches, tuple) or any(type(x) is not int or x < 1 for x in self.update_batches):
            raise ValueError("retain a tuple of explicit adaptation batches")
        if tuple(sorted(set(self.update_batches))) != self.update_batches:
            raise ValueError("adaptation batches must be unique and ordered")


def runtime_versions():
    """Record the actual scientific runtime alongside every model version."""
    return {"python": platform.python_version(), "sklearn": sklearn.__version__,
            "numpy": np.__version__, "scipy": scipy.__version__, "joblib": joblib.__version__}


def validate_observation(row):
    """Accept only label-free development metadata and observed technical inputs."""
    keys = {"sample_id", "phase", "learning_role", "leakage_group_id", "batch_id", "completed", "features", "observed_facts"}
    if set(row) != keys or row["phase"] != "development":
        raise ValueError("development-only input schema; labels and extra fields forbidden")
    for key in ("sample_id", "leakage_group_id"):
        safe_id(row[key])
    if row["learning_role"] not in {"training", "validation_adaptation", "held_out"}:
        raise ValueError("invalid learning role")
    if type(row["batch_id"]) is not int or row["batch_id"] < 0 or type(row["completed"]) is not bool:
        raise ValueError("explicit batch and completion state required")
    if set(row["features"]) != set(FEATURES):
        raise ValueError("fixed label-free feature schema required")
    for name, value in row["features"].items():
        if type(value) not in (int, float) or not math.isfinite(value):
            raise ValueError("finite numeric features required")
        if name == "failed_request_fraction":
            if not 0 <= value <= 1:
                raise ValueError("failed-request fraction outside [0, 1]")
        elif type(value) is not int or not 0 <= value <= 1_000_000:
            raise ValueError("nonnegative bounded integer counts required")
    if set(row["observed_facts"]) - FACTS or any(type(x) is not bool for x in row["observed_facts"].values()):
        raise ValueError("invalid technical predicates or label-bearing metadata")
    return copy.deepcopy(row)


def feature_matrix(rows):
    """Convert only fixed numeric observations to log-count features in retained order."""
    return np.asarray([[float(row["features"][name]) if name == "failed_request_fraction"
                        else math.log1p(row["features"][name]) for name in FEATURES] for row in rows], dtype=np.float32)


def technical_verdict(facts, target):
    """Evaluate fixed technical predicates without using scenario labels or scores."""
    if target not in TARGETS:
        raise ValueError("unsupported development mapping target")
    required = TARGETS[target]
    if any(facts.get(name) is False for name in required):
        return "violation"
    return "satisfied" if all(facts.get(name) is True for name in required) else "insufficient"


def map_compliance(score, threshold, facts, target):
    """Require anomaly plus corroboration for violations; otherwise preserve unknowns."""
    if not math.isfinite(score) or not math.isfinite(threshold):
        raise ValueError("finite score and threshold required")
    verdict = technical_verdict(facts, target)
    anomaly = score >= threshold
    if anomaly and verdict == "violation":
        return "noncompliant"
    if not anomaly and verdict == "satisfied":
        return "compliant"
    return "unknown"


def clean_reference(row):
    """Exclude known technical violations and incomplete state from fit/update pools."""
    return set(row["observed_facts"]) == FACTS and all(row["observed_facts"].values())


class AdaptiveIsolationMonitor:
    """Fit unlabeled observations and update only on earlier scored validation batches."""

    def __init__(self, config=None):
        """Initialize immutable configuration and an empty in-memory development model."""
        self.config = config or MLConfig()
        self.protocol_sha256 = canonical_sha256({"config": asdict(self.config), "features": FEATURES,
            "transform": "log1p_counts_raw_fraction", "mapping": TARGETS,
            "feature_version": FEATURE_VERSION, "mapping_version": MAPPING_VERSION})
        self._forest = None
        self._groups = {}
        self._scored = {}
        self.history = []

    def _build(self, rows):
        """Fit a fresh forest with fixed hyperparameters and a retained random seed."""
        model = IsolationForest(n_estimators=self.config.trees,
                                max_samples=min(self.config.max_samples, len(rows)),
                                contamination="auto", random_state=self.config.seed, n_jobs=1)
        return model.fit(feature_matrix(rows))

    def _scores(self, model, rows):
        """Orient sklearn's normality scores so larger values mean more anomalous."""
        scores = -model.score_samples(feature_matrix(rows))
        if not np.isfinite(scores).all():
            raise ValueError("model produced nonfinite scores")
        return scores

    def _version(self, model, pool, threshold, generation):
        """Hash fitted state, source inputs, parameters and runtime versions together."""
        # Hash typed node fields rather than binary serialization padding.
        trees = []
        for estimator in model.estimators_:
            state = estimator.tree_.__getstate__()
            trees.append({"nodes": {name: state["nodes"][name].tolist() for name in state["nodes"].dtype.names},
                          "values": state["values"].tolist()})
        fitted = {"trees": trees, "max_samples": int(model.max_samples_),
                  "features": [values.tolist() for values in model.estimators_features_]}
        return canonical_sha256({"forest_sha256": canonical_sha256(fitted), "protocol_sha256": self.protocol_sha256,
            "training_sha256": canonical_sha256(pool), "calibration_sha256": canonical_sha256(self._anchor),
            "config": asdict(self.config), "threshold": threshold, "generation": generation,
            "runtime": runtime_versions(),
            "feature_version": FEATURE_VERSION, "mapping_version": MAPPING_VERSION})

    def fit(self, training, calibration):
        """Fit training only and calibrate a threshold on a separate unlabeled anchor."""
        if self._forest is not None:
            raise ValueError("fit once; later changes must use bounded adaptation")
        training = [validate_observation(row) for row in training]
        calibration = [validate_observation(row) for row in calibration]
        if not self.config.min_training <= len(training) <= self.config.max_training_rows or len(calibration) < self.config.min_calibration:
            raise ValueError("insufficient or excessive reference samples")
        if any(row["learning_role"] != "training" for row in training) or any(row["learning_role"] != "validation_adaptation" for row in calibration):
            raise ValueError("held-out data cannot fit or calibrate the model")
        rows = training + calibration
        if len({row["sample_id"] for row in rows}) != len(rows):
            raise ValueError("reference sample IDs must be unique")
        if any(not row["completed"] or not clean_reference(row) for row in rows):
            raise ValueError("reference pool must be complete and technically clean")
        train_groups = {row["leakage_group_id"] for row in training}
        if train_groups & {row["leakage_group_id"] for row in calibration}:
            raise ValueError("related groups overlap training and calibration")
        model = self._build(training)
        threshold = float(np.quantile(self._scores(model, calibration), self.config.calibration_quantile, method="higher"))
        self._anchor = calibration
        version = self._version(model, training, threshold, 0)
        self._forest, self._pool, self.threshold, self.version = model, training, threshold, version
        self._initial_threshold = threshold
        self._minimum_batch = max(row["batch_id"] for row in rows) + 1
        self._last_scored_batch = self._minimum_batch - 1
        self._updates = 0
        self._groups = {row["leakage_group_id"]: row["learning_role"] for row in rows}
        return self

    def predict(self, row, target):
        """Score unseen observations without updating the model or reading answer keys."""
        if self._forest is None:
            raise ValueError("fit the model first")
        row = validate_observation(row)
        if row["learning_role"] not in {"validation_adaptation", "held_out"} or row["batch_id"] < self._minimum_batch:
            raise ValueError("observation is not an eligible unseen evaluation")
        if row["sample_id"] in {x["sample_id"] for x in self._pool + self._anchor}:
            raise ValueError("fitted or calibration observation cannot count as unseen")
        group = row["leakage_group_id"]
        if group in self._groups and self._groups[group] != row["learning_role"]:
            raise ValueError("related group crosses learning roles")
        digest = canonical_sha256(row)
        if row["sample_id"] in self._scored and self._scored[row["sample_id"]]["digest"] != digest:
            raise ValueError("sample ID reused with different evidence")
        score = float(self._scores(self._forest, [row])[0])
        outcome = map_compliance(score, self.threshold, row["observed_facts"], target)
        self._groups[group] = row["learning_role"]
        self._scored[row["sample_id"]] = {"digest": digest, "version": self.version, "outcome": outcome}
        self._last_scored_batch = max(self._last_scored_batch, row["batch_id"])
        return {"outcome": outcome, "anomaly_score": score, "threshold": self.threshold,
                "model_version": self.version, "feature_version": FEATURE_VERSION,
                "mapping_version": MAPPING_VERSION, "adaptation_version": str(self._updates),
                "observation_sha256": digest, "mapping_target": target}

    def adapt(self, observations, next_batch, receipts):
        """Commit bounded updates from earlier completed validation data or retain old state."""
        if self._forest is None:
            raise ValueError("fit before adaptation")
        before = self.version
        try:
            if type(next_batch) is not int or next_batch not in self.config.update_batches or next_batch <= self._last_scored_batch or next_batch <= self._minimum_batch or self._updates >= self.config.max_updates:
                raise ValueError("adaptation is outside the predefined future batch schedule")
            rows = [validate_observation(row) for row in observations]
            ids = {row["sample_id"] for row in rows}
            if not rows or len(ids) != len(rows) or len(rows) > self.config.max_new_rows:
                raise ValueError("duplicate, empty or oversized adaptation batch")
            if ids & {row["sample_id"] for row in self._pool + self._anchor}:
                raise ValueError("adaptation would reuse fitted or calibration data")
            receipt_hashes = {}
            for row in rows:
                if row["learning_role"] != "validation_adaptation" or not row["completed"] or row["batch_id"] >= next_batch:
                    raise ValueError("only previous completed validation batches may adapt")
                prior = self._scored.get(row["sample_id"])
                if not prior or prior["digest"] != canonical_sha256(row):
                    raise ValueError("score each observation before adaptation")
                envelope = json.loads(Path(receipts[row["sample_id"]]).read_text())
                record = envelope["payload"]
                if envelope["payload_sha256"] != canonical_sha256(record):
                    raise ValueError("saved prediction checksum mismatch")
                expected = ("development", "validation_adaptation", row["sample_id"], "ai", self.protocol_sha256)
                actual = tuple(record[key] for key in ("phase", "learning_role", "trial_id", "monitor", "protocol_sha256"))
                if actual != expected or record["provenance"]["observation_sha256"] != prior["digest"] or record["provenance"]["model_version"] != prior["version"] or record["outcome"] != prior["outcome"]:
                    raise ValueError("saved prediction does not match the earlier determination")
                receipt_hashes[row["sample_id"]] = canonical_sha256(envelope)
                if not clean_reference(row):
                    raise ValueError("known violations or incomplete facts cannot enter adaptation")
            pool = self._pool + rows
            if len(pool) > self.config.max_training_rows or len(rows) / len(pool) > self.config.max_new_fraction:
                raise ValueError("adaptation exceeds pool or contamination-fraction bounds")
            candidate = self._build(pool)
            old_scores = self._scores(self._forest, self._anchor)
            candidate_scores = self._scores(candidate, self._anchor)
            if float(np.max(np.abs(candidate_scores - old_scores))) > self.config.max_anchor_score_shift:
                raise ValueError("candidate changes anchor scores beyond the rollback bound")
            raw = float(np.quantile(candidate_scores, self.config.calibration_quantile, method="higher"))
            lower = max(self.threshold - self.config.max_threshold_step, self._initial_threshold - self.config.max_threshold_total)
            upper = min(self.threshold + self.config.max_threshold_step, self._initial_threshold + self.config.max_threshold_total)
            threshold = float(np.clip(raw, lower, upper))
            version = self._version(candidate, pool, threshold, self._updates + 1)
        except Exception as error:
            self.history.append({"accepted": False, "before": before, "next_batch": next_batch, "reason": str(error)})
            raise
        self._forest, self._pool, self.threshold, self.version = candidate, pool, threshold, version
        self._updates += 1
        self._minimum_batch = next_batch
        self.history.append({"accepted": True, "before": before, "after": version,
                             "next_batch": next_batch, "source_samples": sorted(ids), "threshold": threshold,
                             "receipt_sha256": receipt_hashes})
        return version

    def save_artifact(self, destination):
        """Retain fitted state, unlabeled source inputs and a checksummed version manifest."""
        if self._forest is None:
            raise ValueError("no fitted model to save")
        destination = Path(destination)
        destination.mkdir(parents=True, exist_ok=False)
        model_path = destination / "forest.joblib"
        joblib.dump(self._forest, model_path, compress=3)
        manifest = {"status": "development_only_not_frozen", "model_version": self.version,
                    "feature_version": FEATURE_VERSION, "mapping_version": MAPPING_VERSION,
                    "protocol_sha256": self.protocol_sha256, "config": asdict(self.config), "threshold": self.threshold,
                    "initial_threshold": self._initial_threshold, "updates": self._updates,
                    "runtime": runtime_versions(),
                    "model_sha256": hashlib.sha256(model_path.read_bytes()).hexdigest(),
                    "history": self.history}
        (destination / "manifest.json").write_text(json.dumps(manifest, indent=2, allow_nan=False) + "\n")
        (destination / "source-observations.json").write_text(json.dumps({"training": self._pool, "calibration": self._anchor}, indent=2) + "\n")
        for path in destination.iterdir():
            os.chmod(path, 0o600)
        return manifest
