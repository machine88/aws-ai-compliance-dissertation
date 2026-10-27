"""Synthetic integration checks for assigned observations and paired evidence persistence."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from research.catalog import canonical_sha256
from research.controller import DevelopmentController, evaluate_pair, read_private_json
from research.ml import MLConfig
from scripts.controller_smoke import bound_fixtures, synthetic_baseline, synthetic_design


class ControllerTests(unittest.TestCase):
    """Check controller wiring without live AWS services or real experimental observations."""

    def setUp(self):
        """Prepare a visibly synthetic design that can exercise three learning roles.

        Inputs:
            Repository draft definitions; their real overlap grouping is not modified.

        Outputs:
            None: Retains copied synthetic catalog, answer key and assignment fixtures.
        """
        self.catalog, self.truth, self.assignments = synthetic_design()

    def fitted(self, root):
        """Fit an isolated controller using assigned synthetic reference observations.

        Inputs:
            root: New private directory for this test's controller records.

        Outputs:
            DevelopmentController: Fitted monitor bound to the synthetic design.
        """
        controller = DevelopmentController(root, self.catalog, self.assignments, canonical_sha256(self.truth), MLConfig(trees=32))
        controller.fit(self.rows("training", 64, 0, "fit"), self.rows("validation_adaptation", 32, 1, "anchor"))
        return controller

    def rows(self, role, count, batch, prefix):
        """Create synthetic scenario envelopes matching the retained test manifest.

        Inputs:
            role: Learning partition to exercise.
            count: Number of fake observations.
            batch: Completed development batch number.
            prefix: Unique sample-ID prefix.

        Outputs:
            list[dict]: Assigned synthetic observations without expected labels.
        """
        return bound_fixtures(self.catalog, self.assignments, role, count, batch, prefix)

    def test_assignment_binding_rejects_forged_roles_and_groups(self):
        """Refuse caller metadata that disagrees with the retained scenario assignment.

        Inputs:
            Synthetic envelopes with an altered learning role or overlap group.

        Outputs:
            None: Assertions require rejection before any pair directory is created.
        """
        with tempfile.TemporaryDirectory() as directory:
            controller = self.fitted(Path(directory) / "run")
            for field, value in [("learning_role", "training"), ("leakage_group_id", "other-group")]:
                envelope = self.rows("held_out", 1, 2, "probe")[0]
                envelope["observation"][field] = value
                with self.assertRaisesRegex(ValueError, "assigned role"):
                    controller.run_pair(envelope, synthetic_baseline(envelope))
            self.assertFalse((controller.root / "development").exists())

    def test_baseline_evidence_and_label_fields_are_checked(self):
        """Require a real pairing identity and refuse answers disguised as adapter input.

        Inputs:
            A baseline adapter fixture with either a changed evidence hash or extra label.

        Outputs:
            None: Assertions require both malformed adapter inputs to fail.
        """
        with tempfile.TemporaryDirectory() as directory:
            controller = self.fitted(Path(directory) / "run")
            envelope = self.rows("held_out", 1, 2, "probe")[0]
            baseline = synthetic_baseline(envelope)
            baseline["observation_sha256"] = "0" * 64
            with self.assertRaisesRegex(ValueError, "different observation"):
                controller.run_pair(envelope, baseline)
            baseline = synthetic_baseline(envelope)
            baseline["expected"] = "compliant"
            with self.assertRaisesRegex(ValueError, "only adapter output"):
                controller.run_pair(envelope, baseline)

    def test_pair_then_delayed_evaluation_preserves_unknown(self):
        """Store matched predictions before joining the separately authored answer.

        Inputs:
            One assigned synthetic held-out observation and an explicit unknown baseline.

        Outputs:
            None: Assertions verify context, retained unknown, delayed join and overwrite rejection.
        """
        with tempfile.TemporaryDirectory() as directory:
            controller = self.fitted(Path(directory) / "run")
            envelope = self.rows("held_out", 1, 2, "probe")[0]
            trial = envelope["observation"]["sample_id"]
            with self.assertRaises(FileNotFoundError):
                evaluate_pair(controller.root, "held_out", trial, self.catalog, self.truth, self.assignments)
            result = controller.run_pair(envelope, synthetic_baseline(envelope))
            self.assertEqual(result["pair_state"], "complete")
            for path in result["paths"].values():
                self.assertEqual(read_private_json(path)["context"], controller.context)
            joined = evaluate_pair(controller.root, "held_out", trial, self.catalog, self.truth, self.assignments)
            self.assertEqual(joined["predictions"]["baseline"]["outcome"], "unknown")
            self.assertEqual(joined["ground_truth_sha256"], canonical_sha256(self.truth))
            self.assertIn("anomaly_score", joined["ai_details"])
            with self.assertRaises(FileExistsError):
                controller.run_pair(envelope, synthetic_baseline(envelope))
            with self.assertRaises(FileExistsError):
                evaluate_pair(controller.root, "held_out", trial, self.catalog, self.truth, self.assignments)

    def test_partial_writes_cannot_enter_evaluation(self):
        """Retain incomplete pair evidence rather than silently retrying or evaluating it.

        Inputs:
            A synthetic write failure after the first prediction is saved.

        Outputs:
            None: Assertions require an incomplete status, retained output and refused evaluation.
        """
        from research.trials import write_prediction
        with tempfile.TemporaryDirectory() as directory:
            controller = self.fitted(Path(directory) / "run")
            envelope = self.rows("held_out", 1, 2, "partial")[0]
            trial = envelope["observation"]["sample_id"]
            # Fail only the second write to exercise the actual partial-commit boundary.
            with patch("research.controller.write_prediction", side_effect=[write_prediction, OSError("synthetic disk error")]) as writer:
                def first_then_fail(*args, **kwargs):
                    """Write the first receipt and inject a failure for the second.

                    Inputs:
                        args: Positional arguments forwarded to the real prediction writer.
                        kwargs: Keyword arguments forwarded to the real prediction writer.

                    Outputs:
                        Path: First saved prediction; the second call raises OSError.
                    """
                    if writer.call_count == 1:
                        return write_prediction(*args, **kwargs)
                    raise OSError("synthetic disk error")
                writer.side_effect = first_then_fail
                with self.assertRaises(OSError):
                    controller.run_pair(envelope, synthetic_baseline(envelope))
            pair_dir = controller.root / "development/held_out" / trial
            self.assertTrue((pair_dir / "baseline.json").exists())
            self.assertEqual(read_private_json(pair_dir / "status.json")["pair_state"], "incomplete")
            with self.assertRaisesRegex(ValueError, "incomplete"):
                evaluate_pair(controller.root, "held_out", trial, self.catalog, self.truth, self.assignments)

    def test_only_complete_validation_pairs_can_adapt(self):
        """Wire controller receipts into bounded adaptation and reject held-out updates.

        Inputs:
            Eight saved validation pairs followed by one held-out observation.

        Outputs:
            None: Assertions require one versioned update and refusal of held-out adaptation.
        """
        with tempfile.TemporaryDirectory() as directory:
            controller = self.fitted(Path(directory) / "run")
            validation = self.rows("validation_adaptation", 8, 3, "adapt")
            with self.assertRaises(FileNotFoundError):
                controller.adapt(validation, 4)
            for envelope in validation:
                controller.run_pair(envelope, synthetic_baseline(envelope))
            previous = controller.monitor.version
            controller.adapt(validation, 4)
            self.assertNotEqual(controller.monitor.version, previous)
            self.assertEqual(len(list((controller.root / "models").iterdir())), 2)
            heldout = self.rows("held_out", 1, 4, "probe")[0]
            controller.run_pair(heldout, synthetic_baseline(heldout))
            with self.assertRaisesRegex(ValueError, "only assigned validation"):
                controller.adapt([heldout], 6)

    def test_changed_design_or_pair_context_cannot_join(self):
        """Reject another design or altered context even when JSON remains well formed.

        Inputs:
            A saved synthetic pair and deliberately modified design/context metadata.

        Outputs:
            None: Assertions require mismatch errors instead of an evaluation record.
        """
        with tempfile.TemporaryDirectory() as directory:
            controller = self.fitted(Path(directory) / "run")
            envelope = self.rows("held_out", 1, 2, "probe")[0]
            trial = envelope["observation"]["sample_id"]
            result = controller.run_pair(envelope, synthetic_baseline(envelope))
            modified = copy.deepcopy(self.catalog)
            modified["scenarios"][0]["condition"] = "changed"
            with self.assertRaisesRegex(ValueError, "does not match"):
                evaluate_pair(controller.root, "held_out", trial, modified, self.truth, self.assignments)
            modified_truth = copy.deepcopy(self.truth)
            modified_truth["entries"]["S001"]["expected"] = "noncompliant"
            modified_truth["entries"]["S002"]["expected"] = "compliant"
            with self.assertRaisesRegex(ValueError, "design changed"):
                evaluate_pair(controller.root, "held_out", trial, self.catalog, modified_truth, self.assignments)
            path = result["paths"]["baseline"]
            record = json.loads(path.read_text())
            record["payload"]["context"]["catalog_sha256"] = "0" * 64
            record["payload_sha256"] = canonical_sha256(record["payload"])
            path.write_text(json.dumps(record))
            with self.assertRaisesRegex(ValueError, "different catalog"):
                evaluate_pair(controller.root, "held_out", trial, self.catalog, self.truth, self.assignments)

    def test_instrument_failures_cannot_enter_adaptation(self):
        """Retain an instrumentation failure while refusing to learn from that pair.

        Inputs:
            A saved validation pair whose baseline reports instrument_failure.

        Outputs:
            None: Assertions require an adaptation rejection with no model change.
        """
        with tempfile.TemporaryDirectory() as directory:
            controller = self.fitted(Path(directory) / "run")
            envelope = self.rows("validation_adaptation", 1, 3, "failure")[0]
            baseline = synthetic_baseline(envelope)
            baseline["outcome"] = "instrument_failure"
            controller.run_pair(envelope, baseline)
            previous = controller.monitor.version
            with self.assertRaisesRegex(ValueError, "instrument-failure"):
                controller.adapt([envelope], 4)
            self.assertEqual(controller.monitor.version, previous)

    def test_artifact_failure_blocks_subsequent_pairs(self):
        """Stop the controller if an accepted update cannot retain its fitted artifact.

        Inputs:
            A synthetic model-artifact write failure after a valid update is accepted.

        Outputs:
            None: Assertions require the IO error and blocked subsequent pair execution.
        """
        with tempfile.TemporaryDirectory() as directory:
            controller = self.fitted(Path(directory) / "run")
            validation = self.rows("validation_adaptation", 8, 3, "adapt")
            for envelope in validation:
                controller.run_pair(envelope, synthetic_baseline(envelope))
            with patch.object(controller.monitor, "save_artifact", side_effect=OSError("synthetic artifact failure")):
                with self.assertRaises(OSError):
                    controller.adapt(validation, 4)
            heldout = self.rows("held_out", 1, 4, "probe")[0]
            with self.assertRaisesRegex(ValueError, "controller blocked"):
                controller.run_pair(heldout, synthetic_baseline(heldout))
