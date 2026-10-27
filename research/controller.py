"""Offline development controller binding scenarios, model inputs and paired evidence."""
import copy
import json
import os
from pathlib import Path
from research.catalog import canonical_sha256, validate_assignments, validate_catalog
from research.contracts import PROPOSAL_SHA256, WINDOW_SECONDS
from research.ml import AdaptiveIsolationMonitor, TARGETS, validate_observation
from research.trials import OUTCOMES, join_for_evaluation, safe_id, write_prediction


def write_private_json(path, payload):
    """Write a new checksummed development record without replacing earlier evidence.

    Inputs:
        path: New JSON output path beneath the private development run.
        payload: Finite JSON-serializable metadata or evidence to retain.

    Outputs:
        Path: Created mode-600 file containing the payload and its content hash.
    """
    envelope = {"payload": payload, "payload_sha256": canonical_sha256(payload)}
    # Exclusive creation makes repeated or conflicting writes fail visibly.
    with Path(path).open("x") as stream:
        json.dump(envelope, stream, indent=2, sort_keys=True, allow_nan=False)
    os.chmod(path, 0o600)
    return Path(path)


def read_private_json(path):
    """Read retained metadata only after validating its content checksum.

    Inputs:
        path: Existing checksummed JSON record.

    Outputs:
        dict: Original payload; edited or damaged records raise ValueError.
    """
    envelope = json.loads(Path(path).read_text())
    if canonical_sha256(envelope["payload"]) != envelope["payload_sha256"]:
        raise ValueError("development record checksum mismatch")
    return envelope["payload"]


class DevelopmentController:
    """Coordinate development-only decisions without loading an expected-answer file."""

    def __init__(self, root, catalog, assignments, ground_truth_sha256, config=None):
        """Bind an offline run to one source-locked catalog and assignment manifest.

        Inputs:
            root: New private output directory; existing runs are never overwritten.
            catalog: Draft S3 definitions containing explicit technical mapping targets.
            assignments: Complete scenario-to-role manifest matching this catalog hash.
            ground_truth_sha256: Predeclared answer-key file fingerprint; no expected labels enter this controller.
            config: Optional immutable development ML configuration.

        Outputs:
            None: Creates the private run directory and retained label-free design record.
        """
        if not isinstance(ground_truth_sha256, str) or len(ground_truth_sha256) != 64 or any(c not in "0123456789abcdef" for c in ground_truth_sha256):
            raise ValueError("predeclared ground-truth SHA-256 required")
        validate_assignments(catalog, assignments)
        if catalog["proposal_sha256"] != PROPOSAL_SHA256 or catalog["observation_window_seconds"] != WINDOW_SECONDS:
            raise ValueError("controller design differs from the approved proposal")
        # A declaration is still provisional; this controller never claims formal readiness.
        definitions = {row["scenario_id"]: row for row in catalog["scenarios"]}
        if len(definitions) != len(catalog["scenarios"]):
            raise ValueError("duplicate scenario identifiers")
        for row in definitions.values():
            if row["service"] != "S3" or row.get("technical_mapping_target") not in TARGETS:
                raise ValueError("controller currently supports declared S3 development targets only")
            if {"expected", "label", "ground_truth"} & row.keys():
                raise ValueError("expected answers must not enter the controller design")
        self.catalog = copy.deepcopy(catalog)
        self.assignments = copy.deepcopy(assignments)
        self.definitions = copy.deepcopy(definitions)
        self.roles = {row["scenario_id"]: row["learning_role"] for row in assignments["entries"]}
        self.context = {"catalog_sha256": canonical_sha256(catalog), "assignments_sha256": canonical_sha256(assignments),
                        "ground_truth_sha256": ground_truth_sha256}
        self.monitor = AdaptiveIsolationMonitor(config)
        self._ready = False
        # Keep source definitions and assignments beside outputs, with no answer-key values.
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=False)
        os.chmod(self.root, 0o700)
        write_private_json(self.root / "design.json", {"status": "development_only", "context": self.context,
                           "catalog": self.catalog, "assignments": self.assignments})

    def bind(self, envelope):
        """Validate an observation's scenario and role before it can reach the model.

        Inputs:
            envelope: Exactly scenario_id and observation fields; no expected answer.

        Outputs:
            tuple: Matching scenario definition and validated copied observation.
        """
        if set(envelope) != {"scenario_id", "observation"} or envelope["scenario_id"] not in self.definitions:
            raise ValueError("known scenario and label-free observation envelope required")
        row = validate_observation(envelope["observation"])
        definition = self.definitions[envelope["scenario_id"]]
        # Assignments are checked against retained design, not trusted from the caller's row.
        if row["learning_role"] != self.roles[envelope["scenario_id"]] or row["leakage_group_id"] != definition["leakage_group_id"]:
            raise ValueError("observation disagrees with its assigned role or overlap group")
        if not row["completed"]:
            raise ValueError("offline controller requires completed development observations")
        return definition, row

    def fit(self, training, calibration):
        """Bind every reference observation before fitting and calibrating the model.

        Inputs:
            training: Scenario envelopes assigned to the training role.
            calibration: Separate envelopes assigned to validation/adaptation.

        Outputs:
            str: Fitted model version; retains its model artifact but writes no predictions or expected answers.
        """
        # The model separately enforces sample counts, clean references and disjoint groups.
        train_rows = [self.bind(envelope)[1] for envelope in training]
        anchor_rows = [self.bind(envelope)[1] for envelope in calibration]
        self.monitor.fit(train_rows, anchor_rows)
        # A model cannot produce paired records until its fitted state has been retained.
        self.monitor.save_artifact(self.root / "models" / self.monitor.version)
        self._ready = True
        return self.monitor.version

    def run_pair(self, envelope, baseline_decision):
        """Save baseline and AI decisions against exactly the same development evidence.

        Inputs:
            envelope: Completed assigned observation and its scenario identifier.
            baseline_decision: Outcome, source_version and matching observation_sha256 supplied by the baseline adapter.

        Outputs:
            dict: Pair status, AI score metadata and prediction paths; partial writes remain marked incomplete.
        """
        if not self._ready:
            raise ValueError("controller blocked until fitted model artifacts are retained")
        definition, row = self.bind(envelope)
        if set(baseline_decision) != {"outcome", "source_version", "observation_sha256"}:
            raise ValueError("baseline decision must contain only adapter output and evidence identity")
        if baseline_decision["outcome"] not in OUTCOMES or not isinstance(baseline_decision["source_version"], str) or not baseline_decision["source_version"]:
            raise ValueError("explicit baseline outcome and source version required")
        digest = canonical_sha256(row)
        if baseline_decision["observation_sha256"] != digest:
            raise ValueError("baseline used different observation evidence")
        # Reserve a unique pair before scoring so repeated trial IDs cannot replace outcomes.
        directory = self.root / "development" / row["learning_role"] / row["sample_id"]
        directory.mkdir(parents=True, exist_ok=False)
        try:
            write_private_json(directory / "observation.json", {"scenario_id": envelope["scenario_id"], "observation": row})
            prediction = self.monitor.predict(row, definition["technical_mapping_target"])
            shared = {"observation_sha256": digest, "scenario_id": envelope["scenario_id"]}
            ai_provenance = {**shared, **{key: prediction[key] for key in ("model_version", "feature_version", "mapping_version", "adaptation_version")}}
            baseline_provenance = {**shared, "model_version": baseline_decision["source_version"],
                                   "feature_version": "baseline-adapter", "mapping_version": "adapter-supplied-no-fusion",
                                   "adaptation_version": "not-applicable"}
            paths = {}
            for monitor, outcome, provenance in [("baseline", baseline_decision["outcome"], baseline_provenance), ("ai", prediction["outcome"], ai_provenance)]:
                paths[monitor] = write_prediction(self.root, "development", row["learning_role"], row["sample_id"],
                    definition["family_id"], monitor, outcome, provenance, self.monitor.protocol_sha256, context=self.context)
            # The scalar ML score/threshold is retained separately from the label-free decision receipts.
            write_private_json(directory / "ai-details.json", prediction)
        except Exception as error:
            # Retain partial files; an incomplete pair cannot enter evaluation or adaptation.
            write_private_json(directory / "status.json", {"pair_state": "incomplete", "context": self.context,
                               "failure_type": type(error).__name__})
            raise
        write_private_json(directory / "status.json", {"pair_state": "complete", "context": self.context})
        return {"pair_state": "complete", "ai": prediction, "paths": paths}

    def adapt(self, observations, next_batch):
        """Admit only assigned validation observations whose complete pairs are retained.

        Inputs:
            observations: Earlier completed validation scenario envelopes.
            next_batch: Predefined future batch boundary for the proposed update.

        Outputs:
            str: Persisted accepted model version. Rejected candidates retain the active model; artifact IO failure blocks further controller use.
        """
        if not self._ready:
            raise ValueError("controller blocked until fitted model artifacts are retained")
        rows, receipts = [], {}
        for envelope in observations:
            definition, row = self.bind(envelope)
            if row["learning_role"] != "validation_adaptation":
                raise ValueError("only assigned validation observations may adapt")
            directory = self.root / "development" / row["learning_role"] / row["sample_id"]
            status = read_private_json(directory / "status.json")
            if status != {"pair_state": "complete", "context": self.context}:
                raise ValueError("adaptation requires a complete matching pair")
            # Check both receipts and their exact pair identity before model-level eligibility checks.
            if read_private_json(directory / "observation.json") != {"scenario_id": envelope["scenario_id"], "observation": row}:
                raise ValueError("retained observation differs from adaptation source")
            ai = read_private_json(directory / "ai.json")
            baseline = read_private_json(directory / "baseline.json")
            if baseline["outcome"] == "instrument_failure" or ai["outcome"] == "instrument_failure":
                raise ValueError("instrument-failure pairs cannot enter adaptation")
            expected = (row["sample_id"], definition["family_id"], envelope["scenario_id"], canonical_sha256(row), self.monitor.protocol_sha256)
            for monitor, record in [("ai", ai), ("baseline", baseline)]:
                actual = (record["trial_id"], record["family_id"], record["provenance"]["scenario_id"], record["provenance"]["observation_sha256"], record["protocol_sha256"])
                if actual != expected or record.get("context") != self.context or record["monitor"] != monitor or record["learning_role"] != row["learning_role"] or record["phase"] != "development":
                    raise ValueError("saved pair differs from its bound observation or design")
            rows.append(row)
            receipts[row["sample_id"]] = directory / "ai.json"
        version = self.monitor.adapt(rows, next_batch, receipts)
        try:
            self.monitor.save_artifact(self.root / "models" / version)
        except Exception:
            # The candidate was accepted, but cannot be used further if its artifact failed to persist.
            self._ready = False
            raise
        return version


def evaluate_pair(root, learning_role, trial_id, catalog, truth, assignments):
    """Join authored expected answers only after a complete bound pair is saved.

    Inputs:
        root: Controller run directory containing retained design and prediction records.
        learning_role: Assigned validation/adaptation or held-out partition.
        trial_id: Safe identifier of a previously committed prediction pair.
        catalog: Source scenario definitions used by the controller.
        truth: Separate expected-answer specification matching that catalog.
        assignments: Original whole-group learning assignments.

    Outputs:
        dict: Joined development evaluation record, written once with source hashes; no inferential metric is calculated.
    """
    validate_catalog(catalog, truth)
    validate_assignments(catalog, assignments)
    safe_id(trial_id)
    if learning_role not in {"validation_adaptation", "held_out"}:
        raise ValueError("invalid development evaluation role")
    context = {"catalog_sha256": canonical_sha256(catalog), "assignments_sha256": canonical_sha256(assignments),
               "ground_truth_sha256": canonical_sha256(truth)}
    design = read_private_json(Path(root) / "design.json")
    directory = Path(root) / "development" / learning_role / trial_id
    status = read_private_json(directory / "status.json")
    if design["context"] != context or design["catalog"] != catalog or design["assignments"] != assignments or status != {"pair_state": "complete", "context": context}:
        raise ValueError("evaluation design changed or paired outputs are incomplete")
    # Read the recorded scenario identity first, then select its previously authored answer.
    ai = read_private_json(directory / "ai.json")
    scenario = ai["provenance"]["scenario_id"]
    retained = read_private_json(directory / "observation.json")
    if retained["scenario_id"] != scenario or canonical_sha256(retained["observation"]) != ai["provenance"]["observation_sha256"]:
        raise ValueError("saved observation and decision evidence disagree")
    definitions = {row["scenario_id"]: row for row in catalog["scenarios"]}
    roles = {row["scenario_id"]: row["learning_role"] for row in assignments["entries"]}
    if scenario not in truth["entries"] or roles[scenario] != learning_role or ai["family_id"] != definitions[scenario]["family_id"] or ai.get("context") != context:
        raise ValueError("recorded scenario does not match the retained design")
    joined = join_for_evaluation(root, "development", learning_role, trial_id,
                                {"scenario_id": scenario, "expected": truth["entries"][scenario]["expected"]})
    details = read_private_json(directory / "ai-details.json")
    for key in ("model_version", "feature_version", "mapping_version", "adaptation_version", "observation_sha256"):
        if details[key] != ai["provenance"][key]:
            raise ValueError("saved score metadata differs from the AI decision")
    if details["outcome"] != ai["outcome"] or details["mapping_target"] != definitions[scenario]["technical_mapping_target"]:
        raise ValueError("saved score outcome or mapping target differs")
    joined.update({"ai_details": details, "context": context, "ground_truth_sha256": canonical_sha256(truth), "status": "development_only"})
    write_private_json(directory / "evaluation.json", joined)
    return joined
