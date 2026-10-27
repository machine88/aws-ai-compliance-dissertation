"""Test methodological guards using design fixtures, never research observations."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from research.catalog import (assign_learning_roles, canonical_sha256, freeze_bundle,
                              readiness_errors, validate_assignments, validate_catalog)
from research.trials import join_for_evaluation, monitor_input, write_prediction

ROOT = Path(__file__).resolve().parents[1]


class CatalogTests(unittest.TestCase):
    """Protect balance, provenance, family grouping and pre-pilot freeze gates."""

    def setUp(self):
        """Load the separate development definitions and answer key."""
        self.catalog = json.loads((ROOT / "protocol/scenarios/development-s3-v0.1.json").read_text())
        self.truth = json.loads((ROOT / "protocol/ground-truth/development-s3-v0.1.json").read_text())

    def independent_fixture(self):
        """Construct synthetic independence groups solely to exercise assignment logic."""
        catalog = copy.deepcopy(self.catalog)
        for row in catalog["scenarios"]:
            row["leakage_group_id"] = "fixture-group-" + str((int(row["family_id"][1:]) - 1) % 3)
        return catalog

    def test_balanced_design_and_separate_labels(self):
        """Keep each label-by-stratum cell balanced and answers out of catalog rows."""
        result = validate_catalog(self.catalog, self.truth)
        self.assertEqual(result["scenarios"], 12)
        self.assertEqual(set(result["cell_counts"].values()), {3})
        self.catalog["scenarios"][0]["label"] = "noncompliant"
        with self.assertRaises(ValueError):
            validate_catalog(self.catalog, self.truth)

    def test_missing_or_wrong_truth_is_rejected(self):
        """Reject incomplete answer keys and changed proposal provenance."""
        del self.truth["entries"]["S001"]
        with self.assertRaises(ValueError):
            validate_catalog(self.catalog, self.truth)
        self.setUp()
        self.truth["proposal_sha256"] = "0" * 64
        with self.assertRaises(ValueError):
            validate_catalog(self.catalog, self.truth)

    def test_changed_window_and_unsupported_truth_are_rejected(self):
        """Keep the proposal's observation horizon and technical fact schema fixed."""
        self.catalog["observation_window_seconds"] = 60
        with self.assertRaisesRegex(ValueError, "1800-second"):
            validate_catalog(self.catalog, self.truth)
        self.setUp()
        self.truth["entries"]["S001"]["required_facts"]["expected_answer"] = True
        with self.assertRaisesRegex(ValueError, "unsupported"):
            validate_catalog(self.catalog, self.truth)

    def test_overlap_cannot_be_disguised_as_holdout(self):
        """Block three-way splitting of the current overlapping S3 design slice."""
        with self.assertRaisesRegex(ValueError, "independent leakage groups"):
            assign_learning_roles(self.catalog, 997)

    def test_reproducible_assignment_and_leakage_rejection(self):
        """Retain deterministic assignments and reject a related variant moved to holdout."""
        catalog = self.independent_fixture()
        assignment = assign_learning_roles(catalog, 997)
        self.assertEqual(assignment, assign_learning_roles(catalog, 997))
        first = assignment["entries"][0]
        related = next(row for row in assignment["entries"][1:] if row["leakage_group_id"] == first["leakage_group_id"])
        related["learning_role"] = "held_out" if first["learning_role"] != "held_out" else "training"
        with self.assertRaisesRegex(ValueError, "leak"):
            validate_assignments(catalog, assignment)

    def test_manifest_tamper_is_rejected(self):
        """Detect a changed catalog rather than reuse its old partition assignments."""
        catalog = self.independent_fixture()
        assignment = assign_learning_roles(catalog, 997)
        catalog["scenarios"][0]["condition"] = "modified"
        with self.assertRaisesRegex(ValueError, "does not match"):
            validate_assignments(catalog, assignment)

    def test_incomplete_catalog_cannot_freeze(self):
        """Require proposal-wide service coverage and verified assessment mappings."""
        catalog = self.independent_fixture()
        assignment = assign_learning_roles(catalog, 997)
        self.assertTrue(readiness_errors(catalog))
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                freeze_bundle(Path(directory) / "freeze.json", catalog, self.truth, assignment)
            self.assertFalse((Path(directory) / "freeze.json").exists())


class TrialTests(unittest.TestCase):
    """Keep labels out of inputs and prevent evaluation before paired outputs persist."""

    def provenance(self, scenario="S001", observation="b" * 64):
        """Create minimal version metadata for synthetic monitor outputs."""
        return {"model_version": "fixture-model", "feature_version": "fixture-features",
                "mapping_version": "fixture-mapping", "adaptation_version": "none",
                "observation_sha256": observation, "scenario_id": scenario}

    def write_pair(self, root, second_hash="b" * 64):
        """Persist synthetic paired decisions with a shared or deliberately changed input."""
        for monitor, outcome, sha in [("baseline", "unknown", "b" * 64), ("ai", "noncompliant", second_hash)]:
            write_prediction(root, "development", "held_out", "T001", "F01", monitor,
                             outcome, self.provenance(observation=sha), "a" * 64)

    def test_monitor_inputs_reject_labels_and_nested_metadata(self):
        """Accept observed booleans while refusing answer keys and nested label payloads."""
        observed = {"end.tls_deny_present": True}
        self.assertEqual(monitor_input("R001", observed)["observed_facts"], observed)
        for bad in [{"expected": "compliant"}, {"end.tls_deny_present": {"label": True}}]:
            with self.assertRaises(ValueError):
                monitor_input("R001", bad)

    def test_join_requires_both_outputs_and_preserves_unknown(self):
        """Keep absent baseline determinations explicit after both records are saved."""
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(FileNotFoundError):
                join_for_evaluation(directory, "development", "held_out", "T001", {"scenario_id": "S001", "expected": "noncompliant"})
            self.write_pair(directory)
            joined = join_for_evaluation(directory, "development", "held_out", "T001", {"scenario_id": "S001", "expected": "noncompliant"})
            self.assertEqual(joined["predictions"]["baseline"]["outcome"], "unknown")
            with self.assertRaises(FileExistsError):
                self.write_pair(directory)

    def test_mismatched_observations_and_truth_are_rejected(self):
        """Prevent comparing different monitor inputs or joining another scenario's label."""
        with tempfile.TemporaryDirectory() as directory:
            self.write_pair(directory, "c" * 64)
            with self.assertRaisesRegex(ValueError, "same scenario observations"):
                join_for_evaluation(directory, "development", "held_out", "T001", {"scenario_id": "S001", "expected": "noncompliant"})
        with tempfile.TemporaryDirectory() as directory:
            self.write_pair(directory)
            with self.assertRaisesRegex(ValueError, "ground truth"):
                join_for_evaluation(directory, "development", "held_out", "T001", {"scenario_id": "S002", "expected": "noncompliant"})

    def test_formal_recording_and_path_escape_are_blocked(self):
        """Disable formal prediction writing until frozen-catalog controller integration."""
        with tempfile.TemporaryDirectory() as directory:
            for phase, trial in [("pilot", "T001"), ("confirmatory", "T001"), ("development", "../escape")]:
                with self.assertRaises(ValueError):
                    write_prediction(directory, phase, "training", trial, "F01", "ai", "unknown", self.provenance(), "a" * 64)

    def test_tampered_prediction_cannot_be_joined(self):
        """Detect an outcome edited after the immutable prediction was recorded."""
        with tempfile.TemporaryDirectory() as directory:
            self.write_pair(directory)
            path = Path(directory) / "development/held_out/T001/ai.json"
            envelope = json.loads(path.read_text())
            envelope["payload"]["outcome"] = "compliant"
            path.write_text(json.dumps(envelope))
            with self.assertRaisesRegex(ValueError, "checksum"):
                join_for_evaluation(directory, "development", "held_out", "T001", {"scenario_id": "S001", "expected": "noncompliant"})
