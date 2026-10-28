"""Synthetic feature extraction checks; never query AWS or claim research performance."""
import copy
import unittest
from research.aws_reader import ACCOUNT, REGION, BUCKETS
from research.event_features import extract_event_features, STATE_FACTS
from research.ml import validate_observation


class EventFeatureTests(unittest.TestCase):
    """Exercise scope, completeness, deduplication and numeric feature contracts."""

    def setUp(self):
        """Prepare a synthetic closed window and two complete unchanged state snapshots.

        Inputs:
            No arguments; UTC timestamps, booleans and placeholder source hash only.
        Outputs:
            None: Stores fresh event/snapshot/coverage fixtures for every test.
        """
        self.coverage = {"phase": "development", "account_id": ACCOUNT, "region": REGION, "bucket": BUCKETS[0],
                         "window_start": "2026-01-01T00:00:00Z", "window_end": "2026-01-01T00:30:00Z",
                         "closed_at": "2026-01-01T00:31:00Z", "pages_complete": True, "delivery_verified": True,
                         "snapshots_complete": True, "source_manifest_sha256": "a" * 64}
        self.snapshots = [{"observed_at": time, "collector_recorded_at": time, "facts": {name: True for name in STATE_FACTS}}
                          for time in (self.coverage["window_start"], self.coverage["window_end"])]

    def event(self, identifier, name="PutBucketPolicy", failed=False):
        """Create one scoped synthetic management-event envelope.

        Inputs:
            identifier: Unique provider event ID used for deduplication checks.
            name: Proposed S3 operation name in or outside the feature allowlist.
            failed: Whether to attach a top-level synthetic AccessDenied code.
        Outputs:
            dict: Provider event plus collector receipt time, without actual AWS data.
        """
        event = {"eventID": identifier, "eventName": name, "eventSource": "s3.amazonaws.com", "recipientAccountId": ACCOUNT,
                 "awsRegion": REGION, "requestParameters": {"bucketName": BUCKETS[0]}, "eventTime": "2026-01-01T00:01:00Z",
                 "managementEvent": True, "eventCategory": "Management", "readOnly": False, "eventType": "AwsApiCall",
                 "userIdentity": {"principalId": "synthetic-principal"}}
        if failed:
            event["errorCode"] = "AccessDenied"
        return {"event": event, "collector_recorded_at": "2026-01-01T00:01:05Z"}

    def extract(self, events):
        """Run the pure extractor against current synthetic coverage and snapshot fixtures.

        Inputs:
            events: Synthetic envelopes for the current test.
        Outputs:
            dict: Versioned feature result with no file writes or cloud calls.
        """
        return extract_event_features(events, self.snapshots, self.coverage)

    def test_counts_failures_principals_and_state_changes(self):
        """Check exact feature arithmetic across successful and failed attempts.

        Inputs:
            Synthetic policy/public-access/versioning attempts and two changed attributes.
        Outputs:
            None: Asserts proposed counts, unique principals and failed-attempt fraction.
        """
        events = [self.event("one"), self.event("two", "DeleteBucketPolicy"), self.event("three", "PutBucketPublicAccessBlock"), self.event("four", "PutBucketVersioning", True)]
        events[-1]["event"]["userIdentity"]["principalId"] = "second-principal"
        self.snapshots[-1]["facts"]["versioning_enabled"] = False
        self.snapshots[-1]["facts"]["block_public_acls"] = False
        result = self.extract(events)
        self.assertTrue(result["ml_ready"])
        self.assertEqual(result["features"], {"mutation_count": 3, "policy_change_count": 2, "public_access_change_count": 1,
                         "versioning_change_count": 0, "principal_count": 2, "configuration_delta_count": 2, "failed_request_fraction": 0.25})

    def test_duplicate_delivery_is_order_independent(self):
        """Deduplicate provider IDs using their earliest retained receipt.

        Inputs:
            Identical provider event delivered twice, including a later duplicate.
        Outputs:
            None: Asserts one attempt and identical features for reversed input order.
        """
        early = self.event("one")
        late = copy.deepcopy(early)
        late["collector_recorded_at"] = "2026-01-01T00:30:30Z"
        first, second = self.extract([late, early]), self.extract([early, late])
        self.assertEqual(first["features"], second["features"])
        self.assertEqual(first["eligible_attempts"], 1)
        self.assertTrue(first["ml_ready"])

    def test_conflicting_provider_id_rejected(self):
        """Reject changed event bodies sharing one provider identity.

        Inputs:
            Two different mutation operations with the same synthetic ID.
        Outputs:
            None: Asserts ValueError rather than silently choosing a copy.
        """
        with self.assertRaises(ValueError):
            self.extract([self.event("one"), self.event("one", "PutBucketVersioning")])

    def test_unknown_coverage_never_becomes_zero_features(self):
        """Block the entire numeric vector when any completeness declaration is false.

        Inputs:
            Empty event stream under independently missing pages, delivery or snapshots.
        Outputs:
            None: Asserts explicit blockers and no feature values for each condition.
        """
        for key in ("pages_complete", "delivery_verified", "snapshots_complete"):
            coverage = copy.deepcopy(self.coverage)
            coverage[key] = False
            result = extract_event_features([], self.snapshots, coverage)
            self.assertFalse(result["ml_ready"])
            self.assertIsNone(result["features"])
            self.assertIn(key + "_false", result["blockers"])

    def test_declared_complete_quiet_window_has_real_zero_vector(self):
        """Distinguish a declared complete empty history from unavailable history.

        Inputs:
            Complete synthetic coverage and unchanged endpoint snapshots with no events.
        Outputs:
            None: Asserts zero counts while explicitly labeling declaration limits.
        """
        result = self.extract([])
        self.assertTrue(result["ml_ready"])
        self.assertTrue(all(value == 0 for value in result["features"].values()))
        self.assertTrue(result["coverage_is_declaration_not_attestation"])

    def test_polling_and_unrelated_events_are_ignored(self):
        """Exclude read polling, other service/account/region/bucket events.

        Inputs:
            Synthetic polling and mutations outside the declared resource scope.
        Outputs:
            None: Asserts no attempts and retained exclusion counts.
        """
        events = [self.event("read", "GetBucketPolicy")]
        for key, value in (("awsRegion", "us-west-2"), ("recipientAccountId", "999999999999"), ("eventSource", "iam.amazonaws.com")):
            event = self.event(key)
            event["event"][key] = value
            events.append(event)
        other = self.event("other")
        other["event"]["requestParameters"]["bucketName"] = "unrelated"
        events.append(other)
        result = self.extract(events)
        self.assertEqual(result["eligible_attempts"], 0)
        self.assertEqual(sum(result["ignored_counts"].values()), 5)

    def test_missing_attribution_or_identity_blocks(self):
        """Avoid silently dropping an eligible mutation with missing required metadata.

        Inputs:
            Mutations missing bucket, event ID or principal identity in separate cases.
        Outputs:
            None: Asserts no numeric vector and an explicit blocker in each case.
        """
        for key in ("requestParameters", "eventID", "userIdentity"):
            event = self.event("one")
            del event["event"][key]
            result = self.extract([event])
            self.assertFalse(result["ml_ready"])
            self.assertIsNone(result["features"])

    def test_late_delivery_not_retroactively_used(self):
        """Refuse an in-window event that arrived after the scoring cutoff.

        Inputs:
            Source event at one minute with receipt at thirty minutes thirty seconds.
        Outputs:
            None: Asserts an explicit late-delivery blocker rather than retrospective counts.
        """
        event = self.event("one")
        event["collector_recorded_at"] = "2026-01-01T00:30:30Z"
        result = self.extract([event])
        self.assertIn("in_window_event_arrived_after_cutoff", result["blockers"])
        self.assertIsNone(result["features"])

    def test_source_window_and_clock_validation(self):
        """Exclude pre-window events and reject impossible or timezone-naive clocks.

        Inputs:
            Pre-trigger, inverted-receipt and naive-time synthetic variants.
        Outputs:
            None: Asserts exclusion versus explicit malformed-clock rejection.
        """
        event = self.event("one")
        event["event"]["eventTime"] = "2025-12-31T23:59:59Z"
        self.assertEqual(self.extract([event])["ignored_counts"]["outside_source_window"], 1)
        for time in ("2026-01-01T00:02:00Z", "2026-01-01T00:00:00"):
            event["event"]["eventTime"] = time
            with self.assertRaises(ValueError):
                self.extract([event])

    def test_snapshot_gaps_and_conflicts(self):
        """Block missing endpoint/fact coverage and reject contradictory frames.

        Inputs:
            Missing endpoint, missing boolean and same-time conflicting state fixtures.
        Outputs:
            None: Asserts readiness blockers or conflict rejection without invented deltas.
        """
        result = extract_event_features([], self.snapshots[:1], self.coverage)
        self.assertIn("missing_snapshot_endpoints", result["blockers"])
        incomplete = copy.deepcopy(self.snapshots)
        del incomplete[-1]["facts"]["versioning_enabled"]
        self.assertIsNone(extract_event_features([], incomplete, self.coverage)["features"])
        conflict = copy.deepcopy(self.snapshots[-1])
        conflict["facts"]["versioning_enabled"] = False
        with self.assertRaises(ValueError):
            extract_event_features([], self.snapshots + [conflict], self.coverage)

    def test_compatible_with_existing_ml_input_shape(self):
        """Verify numeric compatibility without fitting or evaluating a model.

        Inputs:
            Synthetic extracted vector and a separate development row with no answers.
        Outputs:
            None: Asserts the existing model validator accepts the seven numeric features.
        """
        result = self.extract([self.event("one")])
        row = {"sample_id": "synthetic", "phase": "development", "learning_role": "held_out",
               "leakage_group_id": "synthetic-group", "batch_id": 1, "completed": True,
               "features": result["features"], "observed_facts": {"end.versioning_enabled": True}}
        self.assertEqual(validate_observation(row)["features"], result["features"])

    def test_unsupported_event_or_error_semantics_block(self):
        """Reject unsupported event classifications and nested error layouts.

        Inputs:
            Synthetic mutations misclassified as reads/data/service events or nested failures.
        Outputs:
            None: Asserts a blocked vector rather than silently counting successful changes.
        """
        for key, value in (("managementEvent", False), ("eventCategory", "Data"), ("readOnly", True),
                           ("eventType", "AwsServiceEvent"), ("responseElements", {"Error": "synthetic"})):
            event = self.event("one")
            event["event"][key] = value
            self.assertIsNone(self.extract([event])["features"])

    def test_formal_phase_extra_labels_and_short_window_rejected(self):
        """Preserve development-only and label-free collection contract boundaries.

        Inputs:
            Coverage fixtures with pilot phase, extra answer field or shortened interval.
        Outputs:
            None: Asserts ValueError before feature construction.
        """
        for key, value in (("phase", "pilot"), ("expected", "noncompliant"), ("window_end", "2026-01-01T00:10:00Z")):
            coverage = copy.deepcopy(self.coverage)
            coverage[key] = value
            with self.assertRaises(ValueError):
                extract_event_features([], self.snapshots, coverage)


if __name__ == "__main__":
    unittest.main()
