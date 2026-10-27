"""Exercise the actual estimator and methodological guards using synthetic inputs only."""
import copy
import hashlib
import json
import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path
from unittest.mock import patch
import numpy as np
from research.ml import (AdaptiveIsolationMonitor, MLConfig, feature_matrix,
                         map_compliance, validate_observation)
from scripts.ml_smoke import persist_ai, run_smoke, synthetic_rows


class MLTests(unittest.TestCase):
    """Verify real model behavior without AWS data, ground-truth labels or cloud APIs."""

    def setUp(self):
        """Prepare reproducible, disjoint synthetic fit and calibration partitions."""
        self.training = synthetic_rows(64, "training", 0, 997, "train")
        self.anchor = synthetic_rows(32, "validation_adaptation", 1, 998, "anchor")
        self.config = MLConfig(trees=32)

    def fitted(self):
        """Fit a small actual forest for an isolated test case."""
        return AdaptiveIsolationMonitor(self.config).fit(self.training, self.anchor)

    def update_rows(self, model, root, count=8, batch=3, prefix="update"):
        """Score and persist eligible prior validation decisions before adaptation."""
        rows = synthetic_rows(count, "validation_adaptation", batch, 999, prefix)
        receipts = {row["sample_id"]: persist_ai(root, model, row, model.predict(row, "S3.5")) for row in rows}
        return rows, receipts

    def test_features_and_versions_are_reproducible(self):
        """Train deterministically and retain identical scores and fitted-state versions."""
        first, second = self.fitted(), self.fitted()
        probe = synthetic_rows(1, "held_out", 2, 1000, "probe")[0]
        self.assertEqual(first.version, second.version)
        self.assertEqual(first.predict(probe, "S3.5"), second.predict(probe, "S3.5"))
        self.assertEqual(feature_matrix([probe]).shape, (1, 7))

    def test_score_orientation_matches_sklearn(self):
        """Confirm larger exported scores mean greater anomaly, using actual estimator output."""
        model = self.fitted()
        probe = synthetic_rows(1, "held_out", 2, 1000, "probe")[0]
        expected = -float(model._forest.score_samples(feature_matrix([probe]))[0])
        self.assertAlmostEqual(model.predict(probe, "S3.5")["anomaly_score"], expected)

    def test_mapping_requires_anomaly_and_evidence(self):
        """Refuse to turn benign anomalies, missing facts or low-scoring violations into detections."""
        self.assertEqual(map_compliance(.8, .6, {"end.tls_deny_present": False}, "S3.5"), "noncompliant")
        self.assertEqual(map_compliance(.8, .6, {"end.tls_deny_present": True}, "S3.5"), "unknown")
        self.assertEqual(map_compliance(.4, .6, {"end.tls_deny_present": False}, "S3.5"), "unknown")
        self.assertEqual(map_compliance(.4, .6, {}, "S3.5"), "unknown")
        self.assertEqual(map_compliance(.4, .6, {"end.tls_deny_present": True}, "S3.5"), "compliant")
        self.assertEqual(map_compliance(.8, .6, {"middle.tls_deny_present": False}, "S3_TLS_VERSIONING_WINDOW"), "noncompliant")

    def test_label_nan_and_formal_inputs_are_rejected(self):
        """Block answer-key fields, nonfinite features and pilot/confirmatory use."""
        for change in ("label", "nan", "formal"):
            row = copy.deepcopy(self.training[0])
            if change == "label":
                row["expected"] = "compliant"
            elif change == "nan":
                row["features"]["failed_request_fraction"] = float("nan")
            else:
                row["phase"] = "confirmatory"
            with self.assertRaises(ValueError):
                validate_observation(row)

    def test_heldout_and_overlapping_fit_partitions_are_rejected(self):
        """Exclude held-out rows and related calibration groups before fitting."""
        self.training[0]["learning_role"] = "held_out"
        with self.assertRaisesRegex(ValueError, "held-out"):
            self.fitted()
        self.setUp()
        self.anchor[0]["leakage_group_id"] = self.training[0]["leakage_group_id"]
        with self.assertRaisesRegex(ValueError, "overlap"):
            self.fitted()

    def test_unseen_means_not_previously_fitted_or_calibrated(self):
        """Refuse evaluation that reuses fit data, calibration data or a training group."""
        model = self.fitted()
        for original in (self.training[0], self.anchor[0]):
            row = copy.deepcopy(original)
            row.update(learning_role="held_out", batch_id=2)
            with self.assertRaisesRegex(ValueError, "unseen"):
                model.predict(row, "S3.5")
        row = synthetic_rows(1, "held_out", 2, 1000, "probe")[0]
        row["leakage_group_id"] = self.training[0]["leakage_group_id"]
        with self.assertRaisesRegex(ValueError, "crosses"):
            model.predict(row, "S3.5")

    def test_bounded_adaptation_uses_persisted_earlier_validation(self):
        """Version an accepted update and enforce step, cumulative and replay bounds."""
        model = self.fitted()
        before, threshold = model.version, model.threshold
        with tempfile.TemporaryDirectory() as root:
            rows, receipts = self.update_rows(model, root)
            model.adapt(rows, 4, receipts)
            self.assertNotEqual(before, model.version)
            self.assertLessEqual(abs(model.threshold - threshold), model.config.max_threshold_step + 1e-12)
            self.assertLessEqual(abs(model.threshold - model._initial_threshold), model.config.max_threshold_total + 1e-12)
            self.assertTrue(model.history[-1]["accepted"])
            with self.assertRaises(ValueError):
                model.adapt(rows, 4, receipts)
            with self.assertRaises(ValueError):
                model.predict(rows[0], "S3.5")

    def test_current_heldout_and_unrecorded_updates_are_rejected(self):
        """Prevent adapting on current batches, held-out observations or unsaved predictions."""
        for kind in ("current", "heldout", "unrecorded"):
            model = self.fitted()
            with tempfile.TemporaryDirectory() as root:
                rows, receipts = self.update_rows(model, root)
                if kind == "current":
                    rows[0]["batch_id"] = 4
                elif kind == "heldout":
                    rows[0]["learning_role"] = "held_out"
                else:
                    receipts[rows[0]["sample_id"]].unlink()
                old = model.version
                with self.assertRaises((ValueError, FileNotFoundError)):
                    model.adapt(rows, 4, receipts)
                self.assertEqual(old, model.version)

    def test_contamination_and_oversized_updates_are_rejected(self):
        """Keep known violations and excessive new data out of the adaptive pool."""
        model = self.fitted()
        rows = synthetic_rows(33, "validation_adaptation", 3, 999, "big")
        with self.assertRaisesRegex(ValueError, "oversized"):
            model.adapt(rows, 4, {})
        with tempfile.TemporaryDirectory() as root:
            rows = synthetic_rows(1, "validation_adaptation", 3, 999, "dirty")
            rows[0]["observed_facts"]["end.tls_deny_present"] = False
            receipt = persist_ai(root, model, rows[0], model.predict(rows[0], "S3.5"))
            with self.assertRaisesRegex(ValueError, "known violations"):
                model.adapt(rows, 4, {rows[0]["sample_id"]: receipt})

    def test_anchor_drift_rejection_retains_old_state(self):
        """Roll back a real candidate that exceeds the prespecified anchor-score bound."""
        model = AdaptiveIsolationMonitor(MLConfig(trees=32, max_anchor_score_shift=0.000001)).fit(self.training, self.anchor)
        with tempfile.TemporaryDirectory() as root:
            rows, receipts = self.update_rows(model, root)
            version, threshold = model.version, model.threshold
            with self.assertRaisesRegex(ValueError, "rollback bound"):
                model.adapt(rows, 4, receipts)
            self.assertEqual((model.version, model.threshold), (version, threshold))

    def test_new_data_fraction_and_update_count_are_bounded(self):
        """Enforce proportional intake and total update limits independently of batch size."""
        model = AdaptiveIsolationMonitor(self.config).fit(self.training[:32], self.anchor)
        with tempfile.TemporaryDirectory() as root:
            rows, receipts = self.update_rows(model, root, count=9)
            with self.assertRaisesRegex(ValueError, "fraction bounds"):
                model.adapt(rows, 4, receipts)
        model = AdaptiveIsolationMonitor(MLConfig(trees=32, max_updates=1)).fit(self.training, self.anchor)
        with tempfile.TemporaryDirectory() as root:
            rows, receipts = self.update_rows(model, root)
            model.adapt(rows, 4, receipts)
            later, later_receipts = self.update_rows(model, root, batch=5, prefix="later")
            with self.assertRaisesRegex(ValueError, "schedule"):
                model.adapt(later, 6, later_receipts)

    def test_failed_candidate_retains_old_model(self):
        """Preserve fitted state when candidate training fails before commit."""
        model = self.fitted()
        with tempfile.TemporaryDirectory() as root:
            rows, receipts = self.update_rows(model, root)
            version, threshold = model.version, model.threshold
            with patch.object(model, "_build", side_effect=ValueError("synthetic fit failure")):
                with self.assertRaisesRegex(ValueError, "synthetic fit failure"):
                    model.adapt(rows, 4, receipts)
            self.assertEqual((model.version, model.threshold), (version, threshold))
            self.assertFalse(model.history[-1]["accepted"])

    def test_artifact_is_checksummed_and_not_overwritten(self):
        """Save actual fitted trees and reproducibility inputs in a new private directory."""
        model = self.fitted()
        with tempfile.TemporaryDirectory() as root:
            destination = Path(root) / "artifact"
            manifest = model.save_artifact(destination)
            self.assertEqual(manifest["model_sha256"], hashlib.sha256((destination / "forest.joblib").read_bytes()).hexdigest())
            self.assertEqual(manifest["config"], asdict(model.config))
            self.assertTrue((destination / "source-observations.json").exists())
            with self.assertRaises(FileExistsError):
                model.save_artifact(destination)

    def test_smoke_run_is_explicitly_synthetic(self):
        """Run real fit, adaptation and artifact export without claiming study performance."""
        with tempfile.TemporaryDirectory() as root:
            summary = run_smoke(Path(root) / "smoke")
            self.assertTrue(summary["synthetic_only"])
            self.assertEqual(summary["research_trials"], 0)
            self.assertEqual(summary["accepted_adaptation_updates"], 1)
