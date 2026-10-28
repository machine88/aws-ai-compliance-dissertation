"""Synthetic-only snapshot adaptation tests; no live evidence, AWS access or study metrics."""
import copy
import json
import unittest
from research.aws_reader import ACCOUNT, BUCKETS, READER_PREFIX, read_plan
from research.observations import normalize_snapshot, tls_deny_recognized


class ObservationTests(unittest.TestCase):
    """Guard partial observations, source separation and missing ML event history."""

    def setUp(self):
        """Build a scoped synthetic snapshot with identity, guard responses and completion.

        Inputs:
            No arguments; synthetic fixed bucket/request metadata only.
        Outputs:
            None: Stores a minimal snapshot and its fixed request plan for each test.
        """
        self.bucket = BUCKETS[0]
        self.plan = read_plan(self.bucket)
        self.records = [
            {"kind": "identity", "phase": "development", "response": {"Account": ACCOUNT, "Arn": READER_PREFIX + "synthetic"}},
            self.response("get_bucket_location", {"LocationConstraint": "us-east-2"}),
            self.response("get_bucket_tagging", {"TagSet": [{"Key": "Project", "Value": "aws-ai-compliance-dissertation"}]}),
            {"kind": "completion", "phase": "development", "complete": True, "receipts": []}]

    def response(self, operation, body):
        """Construct one decoded response envelope from a maintained request.

        Inputs:
            operation: Fixed operation whose first matching request should be used.
            body: Synthetic JSON-compatible AWS response.
        Outputs:
            dict: Development envelope with a fixed collector timestamp.
        """
        return {"kind": "response", "phase": "development", "request": copy.deepcopy(next(r for r in self.plan if r["operation"] == operation)),
                "collector_recorded_at": "2026-01-01T00:01:00Z", "response": body}

    def adapted(self, extras):
        """Insert synthetic observations before the capture completion marker.

        Inputs:
            extras: Additional response/error envelopes without expected-answer labels.
        Outputs:
            dict: Pure adapter result; no files or cloud side effects.
        """
        return normalize_snapshot(self.records[:-1] + extras + self.records[-1:], self.bucket)

    def test_snapshot_does_not_invent_ml_counts(self):
        """Refuse ML readiness and interval coverage even when capture declares completion.

        Inputs:
            Minimal successful snapshot with no event history.
        Outputs:
            None: Asserts missing inputs, no numeric features and no fused baseline decision.
        """
        result = self.adapted([])
        self.assertFalse(result["ml_ready"])
        self.assertFalse(result["interval_coverage_established"])
        self.assertNotIn("features", result)
        self.assertEqual(result["baseline_fusion"], "unresolved")
        self.assertEqual(result["observed_facts"], {})
        self.assertTrue(result["missing_response_operations"])

    def test_explicit_booleans_only(self):
        """Retain false protections while leaving omitted or mistyped flags unknown.

        Inputs:
            Partial synthetic public-access settings.
        Outputs:
            None: Asserts false is preserved and absent/string fields are not invented.
        """
        result = self.adapted([self.response("get_public_access_block", {"PublicAccessBlockConfiguration": {"BlockPublicAcls": False, "IgnorePublicAcls": True, "BlockPublicPolicy": "true"}})])
        self.assertEqual(result["observed_facts"], {"end.block_public_acls": False, "end.ignore_public_acls": True})

    def test_versioning_empty_suspended_and_enabled(self):
        """Handle documented never-enabled responses without equating failed reads to absence.

        Inputs:
            Three successful versioning response variants.
        Outputs:
            None: Asserts enabled true, suspended/never-enabled false.
        """
        for status, expected in ((None, False), ("Suspended", False), ("Enabled", True)):
            body = {} if status is None else {"Status": status}
            result = self.adapted([self.response("get_bucket_versioning", body)])
            self.assertEqual(result["observed_facts"]["end.versioning_enabled"], expected)

    def test_missing_policy_differs_from_denied_policy(self):
        """Keep known absent policy separate from unreadable policy.

        Inputs:
            Synthetic missing-policy and AccessDenied envelopes.
        Outputs:
            None: Asserts only known absence establishes a false bucket-policy TLS predicate.
        """
        request = self.response("get_bucket_policy", {})["request"]
        missing = {"kind": "absent", "request": request, "code": "NoSuchBucketPolicy"}
        denied = {"kind": "instrumentation_error", "request": request, "code": "AccessDenied"}
        self.assertFalse(self.adapted([missing])["observed_facts"]["end.tls_deny_present"])
        self.assertNotIn("end.tls_deny_present", self.adapted([denied])["observed_facts"])

    def test_policy_recognition_is_conservative(self):
        """Recognize a sufficient TLS deny without treating unfamiliar semantics as compliance.

        Inputs:
            Synthetic canonical policy, narrowed policy and extra-condition policy.
        Outputs:
            None: Asserts only the conservative sufficient pattern establishes a true fact.
        """
        statement = {"Effect": "Deny", "Principal": "*", "Action": "s3:*", "Resource": [f"arn:aws:s3:::{self.bucket}", f"arn:aws:s3:::{self.bucket}/*"], "Condition": {"Bool": {"aws:SecureTransport": "false"}}}
        self.assertTrue(tls_deny_recognized({"Statement": [statement]}, self.bucket))
        narrowed = copy.deepcopy(statement)
        narrowed["Action"] = "s3:GetObject"
        self.assertFalse(tls_deny_recognized({"Statement": [narrowed]}, self.bucket))
        statement["Condition"]["StringEquals"] = {"aws:PrincipalAccount": ACCOUNT}
        result = self.adapted([self.response("get_bucket_policy", {"Policy": json.dumps({"Statement": [statement]})})])
        self.assertNotIn("end.tls_deny_present", result["observed_facts"])
        self.assertEqual(result["unknown_observations"][0]["kind"], "policy_semantics_unresolved")

    def test_scope_identity_and_phase_rejected(self):
        """Reject missing guards, root identity, unrelated requests and formal phases.

        Inputs:
            Copies of the valid fixture with one scope boundary broken per case.
        Outputs:
            None: Asserts fail-closed ValueError for every malformed snapshot.
        """
        cases = []
        root = copy.deepcopy(self.records)
        root[0]["response"]["Arn"] = f"arn:aws:iam::{ACCOUNT}:root"
        cases.append(root)
        formal = copy.deepcopy(self.records)
        formal[0]["phase"] = "pilot"
        cases.append(formal)
        unrelated = copy.deepcopy(self.records)
        unrelated[1]["request"]["params"]["Bucket"] = "unrelated"
        cases.append(unrelated)
        cases.append(self.records[:1] + self.records[2:])
        for records in cases:
            with self.assertRaises(ValueError):
                normalize_snapshot(records, self.bucket)

    def test_conflicting_snapshots_cannot_overwrite_facts(self):
        """Refuse different observations for a non-paginated request in one snapshot.

        Inputs:
            Two versioning responses with contradictory statuses.
        Outputs:
            None: Asserts conflict rejection instead of last-response-wins behavior.
        """
        with self.assertRaises(ValueError):
            self.adapted([self.response("get_bucket_versioning", {"Status": "Enabled"}), self.response("get_bucket_versioning", {"Status": "Suspended"})])

    def test_config_preserves_unknown_and_original_clocks(self):
        """Retain scoped Config status with pre-trigger timestamps rather than crediting detection.

        Inputs:
            One attributable INSUFFICIENT_DATA evaluation and one unrelated bucket.
        Outputs:
            None: Asserts unchanged status/clock and exclusion of the unrelated result.
        """
        item = {"EvaluationResultIdentifier": {"EvaluationResultQualifier": {"ResourceType": "AWS::S3::Bucket", "ResourceId": self.bucket, "ConfigRuleName": "dissertation-research-public-access-blocks"}, "OrderingTimestamp": "2025-12-31T23:59:00Z"}, "ComplianceType": "INSUFFICIENT_DATA", "ResultRecordedTime": "2026-01-01T00:00:30Z"}
        other = copy.deepcopy(item)
        other["EvaluationResultIdentifier"]["EvaluationResultQualifier"]["ResourceId"] = "unrelated"
        result = self.adapted([self.response("get_compliance_details_by_config_rule", {"EvaluationResults": [item, other]})])
        self.assertEqual(len(result["source_statuses"]), 1)
        self.assertEqual(result["source_statuses"][0]["status"], "INSUFFICIENT_DATA")
        self.assertEqual(result["source_statuses"][0]["source_observed_at"], "2025-12-31T23:59:00Z")

    def test_cspm_rechecks_returned_scope(self):
        """Recheck each ASFF finding instead of trusting request filters alone.

        Inputs:
            Valid synthetic CSPM finding plus findings from wrong account/product/state.
        Outputs:
            None: Asserts one PASSED source status without fused baseline classification.
        """
        finding = {"AwsAccountId": ACCOUNT, "Region": "us-east-2", "ProductName": "Security Hub", "RecordState": "ACTIVE", "Resources": [{"Id": f"arn:aws:s3:::{self.bucket}", "Type": "AwsS3Bucket"}], "Compliance": {"SecurityControlId": "S3.8", "Status": "PASSED"}}
        findings = [finding]
        for key, value in (("AwsAccountId", "999999999999"), ("ProductName", "GuardDuty"), ("RecordState", "ARCHIVED")):
            other = copy.deepcopy(finding)
            other[key] = value
            findings.append(other)
        result = self.adapted([self.response("get_findings", {"Findings": findings})])
        self.assertEqual(len(result["source_statuses"]), 1)
        self.assertEqual(result["source_statuses"][0]["status"], "PASSED")
        self.assertEqual(result["baseline_fusion"], "unresolved")

    def test_incomplete_and_truncated_capture_remains_explicit(self):
        """Keep snapshot completion claims separate from source availability.

        Inputs:
            Truncated findings capture with an explicit incomplete completion marker.
        Outputs:
            None: Asserts incompleteness, unknown/truncation audit and no ML readiness.
        """
        self.records[-1]["complete"] = False
        request = self.response("get_findings", {})["request"]
        result = self.adapted([{"kind": "truncated", "request": request, "resume_token": "synthetic"}])
        self.assertFalse(result["capture_declared_complete"])
        self.assertFalse(result["ml_ready"])
        self.assertEqual(result["unknown_observations"][0]["kind"], "truncated")


if __name__ == "__main__":
    unittest.main()
