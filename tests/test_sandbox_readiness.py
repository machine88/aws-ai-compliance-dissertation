"""Synthetic SDK-shaped regression fixtures for sandbox administrative metadata validation."""
import copy
import json
import unittest
from research.sandbox_readiness import BUCKET, TAGS, verify_sandbox_metadata


def fixture():
    """Construct fresh synthetic metadata using the documented AWS encryption container shape.

    Inputs:
        None: Uses fixed development sandbox identifiers and proposed protection constants.
    Outputs:
        dict: Nine synthetic SDK response payloads, with no AWS calls or captured response IDs.
    """
    return {
        "get_bucket_location": {"LocationConstraint": "us-east-2"},
        "get_bucket_tagging": {"TagSet": [{"Key": k, "Value": v} for k, v in TAGS.items()]},
        "get_public_access_block": {"PublicAccessBlockConfiguration": {k: True for k in ["BlockPublicAcls", "IgnorePublicAcls", "BlockPublicPolicy", "RestrictPublicBuckets"]}},
        "get_bucket_ownership_controls": {"OwnershipControls": {"Rules": [{"ObjectOwnership": "BucketOwnerEnforced"}]}},
        "get_bucket_versioning": {"Status": "Enabled"},
        "get_bucket_encryption": {"ServerSideEncryptionConfiguration": {"Rules": [{"ApplyServerSideEncryptionByDefault": {"SSEAlgorithm": "AES256"}, "BucketKeyEnabled": False, "BlockedEncryptionTypes": {"EncryptionType": ["SSE-C"]}}]}},
        "get_bucket_policy": {"Policy": json.dumps({"Version": "2012-10-17", "Statement": [{"Sid": "RequireTLS", "Effect": "Deny", "Principal": "*", "Action": "s3:*", "Resource": [f"arn:aws:s3:::{BUCKET}", f"arn:aws:s3:::{BUCKET}/*"], "Condition": {"Bool": {"aws:SecureTransport": "false"}}}]})},
        "get_bucket_policy_status": {"PolicyStatus": {"IsPublic": False}},
        "list_objects_v2": {"IsTruncated": False, "KeyCount": 0},
    }


class SandboxReadinessTests(unittest.TestCase):
    """Reject missing or weakened deployment evidence without opening scientific gates."""

    def test_documented_sdk_shape_and_closed_scientific_gates(self):
        """Accept the nested AWS shape while preserving inputs and incomplete readiness gates.

        Inputs:
            self: Test instance using explicitly synthetic metadata.
        Outputs:
            None: Assertions check administrative success, immutable input and false research gates.
        """
        data = fixture(); original = copy.deepcopy(data)
        result = verify_sandbox_metadata(data)
        self.assertEqual(data, original)
        self.assertTrue(result["bucket_protections_match_deployment"])
        for gate in ["source_identity_verified", "source_freshness_verified", "versions_delete_markers_multipart_empty_verified", "trigger_verified", "ml_ready", "formal_trial_authorized"]:
            self.assertIs(result[gate], False)
        self.assertEqual(result["research_trials"], 0)

    def test_flat_or_missing_sse_c_container_rejected(self):
        """Protect the real nested-response regression and reject incomplete encryption evidence.

        Inputs:
            self: Test instance varying only synthetic SSE-C evidence.
        Outputs:
            None: Each unsupported/missing container must fail rather than imply readiness.
        """
        for value in [["SSE-C"], None, {}, {"EncryptionType": []}]:
            with self.subTest(value=value):
                data = fixture()
                data["get_bucket_encryption"]["ServerSideEncryptionConfiguration"]["Rules"][0]["BlockedEncryptionTypes"] = value
                with self.assertRaises(ValueError): verify_sandbox_metadata(data)

    def test_partial_or_nonempty_listing_rejected(self):
        """Prevent truncated, inconsistent or nonempty listings from proving an empty bucket.

        Inputs:
            self: Test instance with explicit malformed/partial synthetic listings.
        Outputs:
            None: Every incomplete/nonempty variant raises ValueError.
        """
        for listing in [{"IsTruncated": True, "KeyCount": 0}, {"IsTruncated": False, "KeyCount": False}, {"IsTruncated": False, "KeyCount": 1}, {"IsTruncated": False, "KeyCount": 0, "Contents": [{"Key": "synthetic"}]}, {"IsTruncated": False, "KeyCount": 0, "NextContinuationToken": "synthetic"}]:
            with self.subTest(listing=listing):
                data = fixture(); data["list_objects_v2"] = listing
                with self.assertRaises(ValueError): verify_sandbox_metadata(data)

    def test_missing_scope_and_false_like_protections_rejected(self):
        """Reject another target, missing metadata and a truthy integer substituted for a boolean.

        Inputs:
            self: Test instance with independent scope/metadata/protection defects.
        Outputs:
            None: All defects fail before an administrative success result is returned.
        """
        with self.assertRaises(ValueError): verify_sandbox_metadata(fixture(), "another-bucket")
        data = fixture(); del data["get_bucket_versioning"]
        with self.assertRaises(ValueError): verify_sandbox_metadata(data)
        data = fixture(); data["get_public_access_block"]["PublicAccessBlockConfiguration"]["BlockPublicPolicy"] = 1
        with self.assertRaises(ValueError): verify_sandbox_metadata(data)

    def test_unreviewed_grant_and_duplicate_policy_key_rejected(self):
        """Reject extra access grants and JSON ambiguity even when other protections look healthy.

        Inputs:
            self: Test instance varying only synthetic bucket policy text.
        Outputs:
            None: Both an extra grant and duplicate JSON field fail validation.
        """
        data = fixture(); policy = json.loads(data["get_bucket_policy"]["Policy"])
        policy["Statement"].append({"Effect": "Allow", "Principal": "*", "Action": "s3:GetObject", "Resource": f"arn:aws:s3:::{BUCKET}/*"})
        data["get_bucket_policy"]["Policy"] = json.dumps(policy)
        with self.assertRaises(ValueError): verify_sandbox_metadata(data)
        data = fixture(); data["get_bucket_policy"]["Policy"] = data["get_bucket_policy"]["Policy"].replace('"Effect": "Deny"', '"Effect": "Allow", "Effect": "Deny"')
        with self.assertRaises(ValueError): verify_sandbox_metadata(data)


if __name__ == "__main__":
    unittest.main()
