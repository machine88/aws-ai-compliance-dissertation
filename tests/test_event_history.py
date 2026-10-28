"""Offline SDK/stub tests for bounded encrypted history inspection; no AWS requests."""
import contextlib
import copy
import io
import json
import unittest
from datetime import datetime, timezone
from unittest.mock import Mock, patch
import boto3
from botocore.stub import Stubber
from research.aws_reader import ACCOUNT, BUCKETS, READER_PREFIX
from research.event_history import history_plan, scoped_events, LookupPacer
from scripts.collect_event_history import main


class HistoryTests(unittest.TestCase):
    """Verify scope, actual SDK pagination, failure status and absence of delivery claims."""

    def setUp(self):
        """Prepare a closed synthetic window and SDK clients with dummy credentials.

        Inputs:
            No external input; synthetic UTC dates and nonfunctional testing credentials.
        Outputs:
            None: Stores fixed plans, stub-ready SDK clients and mock archive/session objects.
        """
        self.now = datetime(2026, 1, 1, 0, 32, tzinfo=timezone.utc)
        self.start, self.end = "2026-01-01T00:00:00Z", "2026-01-01T00:30:00Z"
        self.plan = history_plan(BUCKETS[0], self.start, self.end, self.now)
        session = boto3.Session(aws_access_key_id="testing", aws_secret_access_key="testing", region_name="us-east-2")
        self.sts, self.s3, self.trail = [session.client(service) for service in ("sts", "s3", "cloudtrail")]
        self.archive = Mock(receipts=[])
        self.session = Mock()
        self.session.client.side_effect = [self.sts, self.s3, self.trail]
        self.arguments = ["--start", self.start, "--end", self.end, "--execute-reviewed-read", "--output", "/unused", "--recipient-cert", "/unused-public.pem"]

    def wrapper(self, operation, identifier="synthetic"):
        """Build a synthetic history wrapper with a serialized scoped CloudTrail event.

        Inputs:
            operation: One of the five proposed mutation API names.
            identifier: Provider event ID for identity-consistency checks.
        Outputs:
            dict: JSON-compatible LookupEvents item, not empirical evidence.
        """
        event = {"eventID": identifier, "eventName": operation, "eventSource": "s3.amazonaws.com", "awsRegion": "us-east-2",
                 "recipientAccountId": ACCOUNT, "requestParameters": {"bucketName": BUCKETS[0]}, "eventTime": "2026-01-01T00:01:00Z"}
        return {"EventId": identifier, "EventName": operation, "CloudTrailEvent": json.dumps(event)}

    def guarded_stubs(self, sts, s3):
        """Queue identity, location and tag guards on the active SDK stubbers.

        Inputs:
            sts: Active STS Stubber to receive the expected reader identity.
            s3: Active S3 Stubber to receive Ohio and project-tag guards.
        Outputs:
            None: Adds three synthetic responses; no network requests.
        """
        sts.add_response("get_caller_identity", {"Account": ACCOUNT, "Arn": READER_PREFIX + "synthetic", "UserId": "testing"}, {})
        owner = {"Bucket": BUCKETS[0], "ExpectedBucketOwner": ACCOUNT}
        s3.add_response("get_bucket_location", {"LocationConstraint": "us-east-2"}, owner)
        s3.add_response("get_bucket_tagging", {"TagSet": [{"Key": "Project", "Value": "aws-ai-compliance-dissertation"}]}, owner)

    def execute(self, extra=None):
        """Run main with SDK stub clients, a mock encrypted sink and a fixed clock.

        Inputs:
            extra: Optional additional CLI arguments, such as an item cap.
        Outputs:
            int: Main's status; writes only into the mock sink and captures terminal output.
        """
        with patch("scripts.collect_event_history.EncryptedArchive", return_value=self.archive), contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return main(self.arguments + (extra or []), Mock(return_value=self.session), Mock(return_value=self.now))

    def test_preview_never_acquires_credentials(self):
        """Keep request previews credential-free with one EventName filter per query.

        Inputs:
            Plan-only arguments and a forbidden SDK session constructor.
        Outputs:
            None: Asserts five fixed bounded read requests and zero SDK session creation.
        """
        factory = Mock(side_effect=AssertionError("No session"))
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(["--plan", "--start", self.start, "--end", self.end], factory, Mock(return_value=self.now)), 0)
        factory.assert_not_called()
        self.assertEqual(len(self.plan), 5)
        self.assertTrue(all(len(request["params"]["LookupAttributes"]) == 1 for request in self.plan))

    def test_real_sdk_pagination_and_no_delivery_claim(self):
        """Consume multiple SDK pages while retaining the distinction from delivery completeness.

        Inputs:
            Stubbed bucket guards, two pages for the first mutation and four empty lookups.
        Outputs:
            None: Asserts six encrypted page records, scoped count and delivery_verified=false.
        """
        with Stubber(self.sts) as sts, Stubber(self.s3) as s3, Stubber(self.trail) as trail:
            self.guarded_stubs(sts, s3)
            for index, request in enumerate(self.plan):
                params = {**request["params"], "MaxResults": 50}
                if index == 0:
                    trail.add_response("lookup_events", {"Events": [self.wrapper(request["params"]["LookupAttributes"][0]["AttributeValue"])], "NextToken": "next"}, params)
                    trail.add_response("lookup_events", {"Events": []}, {**params, "NextToken": "next"})
                else:
                    trail.add_response("lookup_events", {"Events": []}, params)
            self.assertEqual(self.execute(), 0)
            trail.assert_no_pending_responses()
        records = [call.args[0] for call in self.archive.write.call_args_list]
        self.assertEqual(len([r for r in records if r["kind"] == "raw_history_page"]), 6)
        self.assertEqual(records[-1]["selected_event_count"], 1)
        self.assertTrue(records[-1]["pages_complete"])
        self.assertFalse(records[-1]["delivery_verified"])
        self.assertFalse(records[-1]["primary_trial_ready"])

    def test_item_cap_preserves_truncation(self):
        """Mark a bounded partial lookup rather than claiming all source events were returned.

        Inputs:
            Two events in the first response with MaxItems=1, plus empty remaining lookups.
        Outputs:
            None: Asserts failing inspection status and a retained continuation record.
        """
        with Stubber(self.sts) as sts, Stubber(self.s3) as s3, Stubber(self.trail) as trail:
            self.guarded_stubs(sts, s3)
            for index, request in enumerate(self.plan):
                operation = request["params"]["LookupAttributes"][0]["AttributeValue"]
                events = [self.wrapper(operation, "one"), self.wrapper(operation, "two")] if index == 0 else []
                trail.add_response("lookup_events", {"Events": events}, {**request["params"], "MaxResults": 50})
            self.assertEqual(self.execute(["--max-items", "1"]), 1)
        records = [call.args[0] for call in self.archive.write.call_args_list]
        self.assertTrue(any(r["kind"] == "truncated" for r in records))
        self.assertFalse(records[-1]["pages_complete"])

    def test_access_denial_is_not_an_empty_success(self):
        """Retain denied-history failures without dropping the remaining independent queries.

        Inputs:
            Five stubbed AccessDenied responses after successful identity/bucket guards.
        Outputs:
            None: Asserts failed status, five explicit errors and no delivery claim.
        """
        with Stubber(self.sts) as sts, Stubber(self.s3) as s3, Stubber(self.trail) as trail:
            self.guarded_stubs(sts, s3)
            for request in self.plan:
                trail.add_client_error("lookup_events", service_error_code="AccessDeniedException", expected_params={**request["params"], "MaxResults": 50})
            self.assertEqual(self.execute(), 1)
        records = [call.args[0] for call in self.archive.write.call_args_list]
        self.assertEqual(len([r for r in records if r["kind"] == "instrumentation_error"]), 5)
        self.assertFalse(records[-1]["pages_complete"])

    def test_wrong_role_stops_before_history(self):
        """Reject a provisioning-user session before any bucket or event-history request.

        Inputs:
            Synthetic IAM-user identity with otherwise unused S3/CloudTrail SDK stubbers.
        Outputs:
            None: Asserts failure and no raw history pages or completed-inspection record.
        """
        with Stubber(self.sts) as sts, Stubber(self.s3), Stubber(self.trail):
            sts.add_response("get_caller_identity", {"Account": ACCOUNT, "Arn": f"arn:aws:iam::{ACCOUNT}:user/martin-morales-personal", "UserId": "testing"}, {})
            self.assertEqual(self.execute(), 1)
        self.assertEqual(self.archive.write.call_count, 0)

    def test_malformed_page_is_not_a_complete_decode(self):
        """Keep successfully fetched but malformed provider data distinct from empty history.

        Inputs:
            A malformed serialized event in the first response, then four empty lookups.
        Outputs:
            None: Asserts failed inspection, retained raw page and decoding_complete=false.
        """
        with Stubber(self.sts) as sts, Stubber(self.s3) as s3, Stubber(self.trail) as trail:
            self.guarded_stubs(sts, s3)
            for index, request in enumerate(self.plan):
                events = [{"CloudTrailEvent": "not-json"}] if index == 0 else []
                trail.add_response("lookup_events", {"Events": events}, {**request["params"], "MaxResults": 50})
            self.assertEqual(self.execute(), 1)
        records = [call.args[0] for call in self.archive.write.call_args_list]
        self.assertTrue(records[-1]["pages_complete"])
        self.assertFalse(records[-1]["decoding_complete"])
        self.assertFalse(records[-1]["delivery_verified"])

    def test_returned_scope_and_identity_rechecked(self):
        """Reject malformed attribution and ignore explicit unrelated resources.

        Inputs:
            Synthetic valid, wrong-bucket, mismatched-ID and malformed-JSON wrappers.
        Outputs:
            None: Asserts one selected envelope plus distinct ignored and issue counts.
        """
        request = self.plan[0]
        operation = request["params"]["LookupAttributes"][0]["AttributeValue"]
        valid = self.wrapper(operation)
        other = copy.deepcopy(valid)
        event = json.loads(other["CloudTrailEvent"])
        event["requestParameters"]["bucketName"] = "unrelated"
        other["CloudTrailEvent"] = json.dumps(event)
        mismatch = copy.deepcopy(valid)
        mismatch["EventId"] = "wrong"
        malformed = {"CloudTrailEvent": "not-json"}
        result = scoped_events({"Events": [valid, other, mismatch, malformed]}, request, BUCKETS[0], self.now.isoformat())
        self.assertEqual(len(result["envelopes"]), 1)
        self.assertEqual(result["ignored_counts"]["other_bucket"], 1)
        self.assertEqual(result["issue_counts"]["malformed_or_unattributable_event"], 2)
        self.assertEqual(result["envelopes"][0]["collector_recorded_at"], self.now.isoformat())

    def test_pacer_spaces_attempts_without_reading_requests(self):
        """Space sequential HTTP sends including retry callbacks without logging signed data.

        Inputs:
            Synthetic monotonic readings and mocked sleep/request objects.
        Outputs:
            None: Asserts a 0.45-second pause on a closely spaced second attempt.
        """
        sleeper = Mock()
        pacer = LookupPacer(Mock(side_effect=[0.0, 0.0, 0.1, 0.55]), sleeper)
        request = Mock()
        pacer.before_send(request)
        pacer.before_send(request)
        self.assertAlmostEqual(sleeper.call_args.args[0], 0.45)
        self.assertEqual(request.mock_calls, [])

    def test_window_and_execution_gate(self):
        """Reject future/outdated/short intervals and require explicit reviewed-read opt-in.

        Inputs:
            Invalid history intervals and otherwise valid CLI arguments lacking execution opt-in.
        Outputs:
            None: Asserts validation errors and no SDK credential/session acquisition.
        """
        for start, end in ((self.start, "2026-01-01T00:10:00Z"), ("2026-01-01T01:00:00Z", "2026-01-01T01:30:00Z"), ("2025-01-01T00:00:00Z", "2025-01-01T00:30:00Z")):
            with self.assertRaises(ValueError):
                history_plan(BUCKETS[0], start, end, self.now)
        factory = Mock()
        args = [item for item in self.arguments if item != "--execute-reviewed-read"]
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            main(args, factory, Mock(return_value=self.now))
        factory.assert_not_called()


if __name__ == "__main__":
    unittest.main()
