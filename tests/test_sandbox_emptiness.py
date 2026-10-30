"""Synthetic full-bucket emptiness boundary tests; no AWS IO or captured evidence."""
import copy
import unittest
from research.sandbox_emptiness import ACCOUNT, BUCKET, LISTINGS, REGION, verify_empty_sandbox_listings


def fixture():
    """Build independent successful empty synthetic first-page listing receipts.

    Inputs:
        None: Uses the fixed development scope and declared listing contract.
    Outputs:
        dict: Fresh synthetic receipts; does not read or write files or call AWS.
    """
    receipts = {}
    for operation, (limit, name, _, _) in LISTINGS.items():
        receipts[operation] = {"region": REGION,
            "request": {"Bucket": BUCKET, "ExpectedBucketOwner": ACCOUNT, limit: 1000},
            "response": {name: BUCKET, "IsTruncated": False, limit: 1000,
                         "ResponseMetadata": {"HTTPStatusCode": 200}}}
    receipts["list_objects_v2"]["response"]["KeyCount"] = 0
    return receipts


class SandboxEmptinessTests(unittest.TestCase):
    """Keep apparent empty pages from overriding incomplete or mismatched scope."""

    def test_empty_responses_preserve_inputs_and_closed_gates(self):
        """Accept omitted empty collections while keeping authorization and freshness closed.

        Inputs:
            self: Test instance using only synthetic receipts.
        Outputs:
            None; asserts immutable inputs and explicit scope of the result.
        """
        receipts = fixture()
        original = copy.deepcopy(receipts)
        result = verify_empty_sandbox_listings(receipts)
        self.assertEqual(receipts, original)
        self.assertIs(result.pop("supplied_listings_empty"), True)
        result.pop("version")
        self.assertTrue(all(value is False or type(value) is int and value == 0 for value in result.values()))

    def test_nonempty_and_malformed_collections_rejected(self):
        """Reject historical objects, deletion markers, uploads, grouped keys and bad types.

        Inputs:
            self: Test instance enumerating every collection and malformed/nonempty variant.
        Outputs:
            None; asserts each variant fails without accessing object bodies.
        """
        for operation, (_, _, collections, _) in LISTINGS.items():
            for field in collections + ("CommonPrefixes",):
                for value in ([{"synthetic": True}], None, {}, ""):
                    with self.subTest(operation=operation, field=field, value=value):
                        receipts = fixture()
                        receipts[operation]["response"][field] = value
                        with self.assertRaises(ValueError):
                            verify_empty_sandbox_listings(receipts)

    def test_filters_pagination_errors_and_identity_rejected(self):
        """Reject request filters, pagination remnants, failures and target mismatches.

        Inputs:
            self: Test instance varying one request or response field at a time.
        Outputs:
            None; asserts fail-closed handling for every operation.
        """
        for operation, (_, name, _, markers) in LISTINGS.items():
            for field, value in [("IsTruncated", True), ("IsTruncated", 0), (name, "other"),
                                 ("Error", {}), ("ResponseMetadata", {"HTTPStatusCode": 403}),
                                 ("Prefix", "subset/"), ("Delimiter", "/")] + [(key, "next") for key in markers]:
                receipts = fixture()
                receipts[operation]["response"][field] = value
                with self.subTest(operation=operation, field=field):
                    with self.assertRaises(ValueError):
                        verify_empty_sandbox_listings(receipts)
            for field, value in (("Prefix", "subset/"), ("ExpectedBucketOwner", "000000000000"), ("Bucket", "other")):
                receipts = fixture()
                receipts[operation]["request"][field] = value
                with self.assertRaises(ValueError):
                    verify_empty_sandbox_listings(receipts)
        receipts = fixture()
        del receipts["list_object_versions"]
        with self.assertRaises(ValueError):
            verify_empty_sandbox_listings(receipts)
        with self.assertRaises(ValueError):
            verify_empty_sandbox_listings(fixture(), "other")

    def test_missing_completion_count_and_region_rejected(self):
        """Reject missing completeness, false-like counts and unbound regional requests.

        Inputs:
            self: Test instance using synthetic incomplete receipt envelopes.
        Outputs:
            None; asserts all missing or malformed completion evidence fails.
        """
        for operation in LISTINGS:
            receipts = fixture()
            del receipts[operation]["response"]["IsTruncated"]
            with self.assertRaises(ValueError):
                verify_empty_sandbox_listings(receipts)
            receipts = fixture()
            receipts[operation]["region"] = "us-east-1"
            with self.assertRaises(ValueError):
                verify_empty_sandbox_listings(receipts)
        for value in (None, False, 1, "0"):
            receipts = fixture()
            receipts["list_objects_v2"]["response"]["KeyCount"] = value
            with self.assertRaises(ValueError):
                verify_empty_sandbox_listings(receipts)


class CombinedPrestateTests(unittest.TestCase):
    """Ensure one successful check cannot bypass a failed companion precondition."""

    def test_combined_prestate_does_not_authorize_execution(self):
        """Require both independent predicates and keep the live execution gate closed.

        Inputs:
            self: Test instance with synthetic protection and listing fixtures.
        Outputs:
            None; asserts combined success and rejection of either weakened input.
        """
        from research.sandbox_emptiness import verify_sandbox_prestate
        from tests.test_sandbox_readiness import fixture as protection_fixture

        result = verify_sandbox_prestate(protection_fixture(), fixture())
        self.assertIs(result["live_execution_allowed"], False)
        self.assertIs(result["protections"]["bucket_protections_match_deployment"], True)
        self.assertIs(result["empty_listings"]["supplied_listings_empty"], True)
        metadata = protection_fixture()
        metadata["get_bucket_versioning"]["Status"] = "Suspended"
        with self.assertRaises(ValueError):
            verify_sandbox_prestate(metadata, fixture())
        receipts = fixture()
        receipts["list_object_versions"]["response"]["DeleteMarkers"] = [{"Key": "synthetic"}]
        with self.assertRaises(ValueError):
            verify_sandbox_prestate(protection_fixture(), receipts)
