"""Offline SDK contract and encrypted-export tests; no AWS calls or research results."""
import contextlib
import io
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import boto3
from botocore.stub import Stubber
from botocore.exceptions import ClientError
from research.aws_reader import ACCOUNT, BUCKETS, READER_PREFIX, EncryptedArchive, check_scope, read_plan, verify_identity
from scripts.collect_snapshot import main


class ReaderTests(unittest.TestCase):
    """Exercise boundaries using real SDK shapes and synthetic local certificates."""

    def test_scope_and_identity(self):
        """Reject unreviewed resources and principals.

        Inputs:
            Synthetic identity responses and bucket guard fixtures.
        Outputs:
            None: Assertions confirm only the dedicated role and scoped bucket pass.
        """
        verify_identity({"Account": ACCOUNT, "Arn": READER_PREFIX + "test"})
        for arn in (f"arn:aws:iam::{ACCOUNT}:root", f"arn:aws:iam::{ACCOUNT}:user/test", "arn:aws:sts::999999999999:assumed-role/dissertation-evidence-reader/test"):
            with self.assertRaises(ValueError):
                verify_identity({"Account": ACCOUNT, "Arn": arn})
        with self.assertRaises(ValueError):
            read_plan("unrelated")
        with self.assertRaises(ValueError):
            check_scope("get_bucket_location", {"LocationConstraint": "us-east-1"})
        with self.assertRaises(ValueError):
            check_scope("get_bucket_tagging", {"TagSet": []})

    def test_plan_never_opens_session(self):
        """Verify preview is credential-free and uses only read operations.

        Inputs:
            Plan-mode arguments and a forbidden mock session constructor.
        Outputs:
            None: Asserts no SDK session and an allowlisted read-only plan.
        """
        factory = Mock(side_effect=AssertionError("Session must not be opened"))
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(["--plan"], factory), 0)
        factory.assert_not_called()
        self.assertTrue(all(item["operation"].startswith(("get_", "describe_")) for item in read_plan(BUCKETS[0])))

    def test_sdk_shapes_and_pagination(self):
        """Validate all request parameters and real SDK paginator behavior offline.

        Inputs:
            Synthetic dummy credentials, fixed read plan and stubbed empty responses.
        Outputs:
            None: Confirms modeled parameters and consumption of two finding pages.
        """
        session = boto3.Session(aws_access_key_id="testing", aws_secret_access_key="testing", region_name="us-east-2")
        clients = {name: session.client(name) for name in ("s3", "config", "securityhub", "cloudtrail")}
        from botocore.validate import validate_parameters
        for request in read_plan(BUCKETS[0]):
            client = clients[request["service"]]
            model = client.meta.service_model.operation_model(client.meta.method_to_api_mapping[request["operation"]])
            validate_parameters(request["params"], model.input_shape)
            if request["paginated"]:
                self.assertTrue(client.can_paginate(request["operation"]))
        client = clients["securityhub"]
        with Stubber(client) as stub:
            stub.add_response("get_findings", {"Findings": [], "NextToken": "next"}, {})
            stub.add_response("get_findings", {"Findings": []}, {"NextToken": "next"})
            pages = list(client.get_paginator("get_findings").paginate())
            self.assertEqual(len(pages), 2)

    def test_capture_errors_are_not_compliance(self):
        """Retain absence and denied-read observations without converting either to compliance.

        Inputs:
            Mocked SDK clients, encrypted sink and valid synthetic scope responses.
        Outputs:
            None: Verifies denied reads produce incomplete status and explicit error records.
        """
        session = Mock()
        client = session.client.return_value
        client.get_caller_identity.return_value = {"Account": ACCOUNT, "Arn": READER_PREFIX + "test"}
        client.get_bucket_location.return_value = {"LocationConstraint": "us-east-2"}
        client.get_bucket_tagging.return_value = {"TagSet": [{"Key": "Project", "Value": "aws-ai-compliance-dissertation"}]}
        client.get_bucket_policy.side_effect = ClientError({"Error": {"Code": "NoSuchBucketPolicy"}}, "GetBucketPolicy")
        client.get_bucket_versioning.side_effect = ClientError({"Error": {"Code": "AccessDenied"}}, "GetBucketVersioning")
        client.get_paginator.return_value.paginate.return_value = []
        archive = Mock(receipts=[])
        # Empty mock paginators have no continuation, matching a fully returned empty source.
        plan = [request for request in read_plan(BUCKETS[0]) if not request["paginated"]]
        with patch("scripts.collect_snapshot.EncryptedArchive", return_value=archive), patch("scripts.collect_snapshot.read_plan", return_value=plan), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(["--output", "/unused", "--recipient-cert", "/unused-public.pem"], Mock(return_value=session)), 1)
        records = [call.args[0] for call in archive.write.call_args_list]
        self.assertTrue(any(record["kind"] == "absent" for record in records))
        self.assertTrue(any(record["kind"] == "instrumentation_error" for record in records))
        self.assertFalse(records[-1]["complete"])

    def test_wrong_identity_stops_resource_reads(self):
        """Stop immediately after STS rejects a non-reader identity.

        Inputs:
            A mock session identifying the account root and a mock encryption sink.
        Outputs:
            None: Asserts failure and no bucket read calls.
        """
        session = Mock()
        client = session.client.return_value
        client.get_caller_identity.return_value = {"Account": ACCOUNT, "Arn": f"arn:aws:iam::{ACCOUNT}:root"}
        with patch("scripts.collect_snapshot.EncryptedArchive"), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(["--output", "/unused", "--recipient-cert", "/unused-public.pem"], Mock(return_value=session)), 1)
        client.get_bucket_location.assert_not_called()

    def test_encrypted_archive_roundtrip(self):
        """Prove raw evidence is encrypted and decrypts to its original JSON.

        Inputs:
            Temporary synthetic RSA certificate/key and a recognizable payload.
        Outputs:
            None: Asserts ciphertext confidentiality, roundtrip, permissions and no overwrite.
        """
        binary = "/opt/homebrew/opt/openssl@3/bin/openssl"
        if not Path(binary).exists():
            binary = shutil.which("openssl")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cert, key = root / "public.pem", root / "test-only.key"
            subprocess.run([binary, "req", "-x509", "-newkey", "rsa:3072", "-nodes", "-keyout", str(key), "-out", str(cert), "-days", "1", "-subj", "/CN=synthetic-test"], check=True, capture_output=True)
            archive = EncryptedArchive(root / "capture", cert, binary)
            receipt = archive.write({"private_marker": "synthetic-evidence-should-be-encrypted"})
            encrypted = (archive.root / receipt["file"]).read_bytes()
            self.assertNotIn(b"synthetic-evidence", encrypted)
            restored = subprocess.run([binary, "cms", "-decrypt", "-binary", "-inform", "DER", "-recip", str(cert), "-inkey", str(key)], input=encrypted, check=True, capture_output=True).stdout
            self.assertEqual(json.loads(restored)["private_marker"], "synthetic-evidence-should-be-encrypted")
            self.assertEqual((archive.root / receipt["file"]).stat().st_mode & 0o777, 0o600)
            with self.assertRaises(FileExistsError):
                EncryptedArchive(root / "capture", cert, binary)


if __name__ == "__main__":
    unittest.main()
