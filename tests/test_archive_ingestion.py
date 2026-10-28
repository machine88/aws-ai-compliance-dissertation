"""Synthetic CMS archive integrity and scope checks; no real private keys or AWS calls."""
import copy
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import Mock
from pathlib import Path
from research.archive_ingestion import verify_archive, verify_history_records
from research.aws_reader import ACCOUNT, BUCKETS, READER_PREFIX, EncryptedArchive, read_plan
from research.event_history import history_plan, scoped_events
from datetime import datetime, timezone


class ArchiveTests(unittest.TestCase):
    """Exercise actual synthetic encryption/decryption and fail-closed archive validation."""

    @classmethod
    def setUpClass(cls):
        """Create one ephemeral synthetic RSA recipient for this offline test class.

        Inputs:
            No arguments; local OpenSSL 3 and temporary test storage only.
        Outputs:
            None: Stores temporary test key/certificate paths and the normalized public-file pin.
        """
        cls.temporary = tempfile.TemporaryDirectory()
        cls.base = Path(cls.temporary.name)
        cls.binary = "/opt/homebrew/opt/openssl@3/bin/openssl" if Path("/opt/homebrew/opt/openssl@3/bin/openssl").exists() else shutil.which("openssl")
        cls.key, cls.certificate = cls.base / "synthetic-only.key", cls.base / "public.pem"
        subprocess.run([cls.binary, "req", "-x509", "-newkey", "rsa:3072", "-nodes", "-keyout", str(cls.key), "-out", str(cls.certificate), "-days", "1", "-subj", "/CN=synthetic-archive-test"], check=True, capture_output=True)
        cls.pin = hashlib.sha256(cls.certificate.read_bytes()).hexdigest()

    @classmethod
    def tearDownClass(cls):
        """Delete the ephemeral synthetic recipient and all temporary archives.

        Inputs:
            Existing class-owned temporary directory.
        Outputs:
            None: Removes test-only files; never touches a user recipient.
        """
        cls.temporary.cleanup()

    def setUp(self):
        """Create a fresh capture directory and synthetic reader identity.

        Inputs:
            No external input; class-owned synthetic public certificate.
        Outputs:
            None: Stores an empty encrypted sink under a unique temporary parent.
        """
        parent = Path(tempfile.mkdtemp(dir=self.base))
        self.archive = EncryptedArchive(parent / "capture", self.certificate, self.binary)
        self.identity = {"kind": "identity", "phase": "development", "response": {"Account": ACCOUNT, "Arn": READER_PREFIX + "synthetic"}}

    def decrypt(self, ciphertext):
        """Authenticate/decrypt synthetic CMS content without writing plaintext or logging key data.

        Inputs:
            ciphertext: One encrypted synthetic record provided by the verifier.
        Outputs:
            bytes: Authenticated plaintext in memory; cryptographic failures raise.
        """
        return subprocess.run([self.binary, "cms", "-decrypt", "-binary", "-inform", "DER", "-recip", str(self.certificate), "-inkey", str(self.key)], input=ciphertext, check=True, capture_output=True).stdout

    def snapshot(self, omit=None, complete=True):
        """Write a complete synthetic snapshot request ledger and its encrypted terminal chain.

        Inputs:
            omit: Optional operation to omit for missing-source tests.
            complete: Explicit completion declaration to place in the terminal marker.
        Outputs:
            None: Writes synthetic ciphertext records, never actual observations.
        """
        self.archive.write(self.identity)
        for request in read_plan(BUCKETS[0]):
            operation = request["operation"]
            if operation == omit:
                continue
            body = {}
            if operation == "get_bucket_location":
                body = {"LocationConstraint": "us-east-2"}
            if operation == "get_bucket_tagging":
                body = {"TagSet": [{"Key": "Project", "Value": "aws-ai-compliance-dissertation"}]}
            if operation == "get_bucket_policy":
                body = {"Policy": json.dumps({"Statement": []})}
            self.archive.write({"kind": "response", "phase": "development", "request": request, "collector_recorded_at": "2026-01-01T00:31:00Z", "response": body})
        self.archive.write({"kind": "completion", "phase": "development", "complete": complete, "receipts": list(self.archive.receipts)})

    def verify(self, **kwargs):
        """Run verification against the synthetic pinned recipient and reviewed bucket.

        Inputs:
            kwargs: Optional verifier limit overrides for boundary tests.
        Outputs:
            dict: In-memory verification result; no raw output or file writes.
        """
        return verify_archive(self.archive.root, self.decrypt, self.pin, BUCKETS[0], **kwargs)

    def test_valid_snapshot_binds_receipts_and_keeps_readiness_limits(self):
        """Verify a genuine synthetic encrypted chain without claiming authenticity or ML readiness.

        Inputs:
            Complete synthetic snapshot including every maintained request.
        Outputs:
            None: Asserts successful binding and explicit false scientific-readiness flags.
        """
        self.snapshot()
        result = self.verify()
        self.assertEqual(result["capture_kind"], "snapshot")
        self.assertFalse(result["sender_authenticated"])
        self.assertFalse(result["provider_delivery_verified"])
        self.assertFalse(result["formal_trial_authorized"])
        self.assertFalse(result["normalized"]["ml_ready"])

    def test_modified_ciphertext_is_rejected(self):
        """Reject encrypted content changed after capture.

        Inputs:
            Synthetic archive with one modified CMS record.
        Outputs:
            None: Asserts a cryptographic or envelope-validation failure.
        """
        self.snapshot()
        path = self.archive.root / "record-00001.cms"
        content = bytearray(path.read_bytes())
        content[-5] ^= 1
        path.write_bytes(content)
        with self.assertRaises((subprocess.SubprocessError, ValueError)):
            self.verify()

    def test_changed_completion_receipts_are_rejected(self):
        """Reject a terminal record that omits predecessor ciphertext hashes.

        Inputs:
            Synthetic identity and an encrypted completion with an empty receipt list.
        Outputs:
            None: Asserts receipt-chain mismatch even though CMS decryption succeeds.
        """
        self.archive.write(self.identity)
        self.archive.write({"kind": "completion", "phase": "development", "complete": True, "receipts": []})
        with self.assertRaises(ValueError):
            self.verify()

    def test_missing_or_incomplete_snapshot_is_rejected(self):
        """Reject a successful-looking terminal marker when required source requests are missing.

        Inputs:
            Snapshot deliberately omitting the bucket versioning operation.
        Outputs:
            None: Asserts missing-source rejection instead of downstream zero/false inference.
        """
        self.snapshot(omit="get_bucket_versioning")
        with self.assertRaises(ValueError):
            self.verify()

    def test_pinned_recipient_limits_and_unexpected_files(self):
        """Reject recipient substitution, excessive records/bytes and unrelated directory entries.

        Inputs:
            Valid synthetic archive with individual verifier constraints and an extra file.
        Outputs:
            None: Asserts failure for every boundary without dumping decrypted records.
        """
        self.snapshot()
        with self.assertRaises(ValueError):
            verify_archive(self.archive.root, self.decrypt, "0" * 64, BUCKETS[0])
        for kwargs in ({"max_records": 2}, {"max_bytes": 10}):
            with self.assertRaises(ValueError):
                self.verify(**kwargs)
        (self.archive.root / "unexpected.txt").write_text("synthetic")
        with self.assertRaises(ValueError):
            self.verify()

    def test_symlinks_broad_permissions_and_missing_records_rejected(self):
        """Refuse unsafe files and gaps before admitting decrypted evidence.

        Inputs:
            Synthetic record with broad permissions, then a symlink replacement and a gap.
        Outputs:
            None: Asserts permission, link and sequence failures.
        """
        self.snapshot()
        path = self.archive.root / "record-00001.cms"
        path.chmod(0o644)
        with self.assertRaises(ValueError):
            self.verify()
        path.chmod(0o600)
        path.unlink()
        path.symlink_to(self.certificate)
        with self.assertRaises((ValueError, OSError)):
            self.verify()
        path.unlink()
        with self.assertRaises(ValueError):
            self.verify()

    def test_ambiguous_json_is_rejected(self):
        """Reject duplicate JSON keys at the trusted decryption boundary.

        Inputs:
            Two encrypted placeholder files and a trusted test callback returning ambiguous JSON.
        Outputs:
            None: Asserts parsing fails before any envelope is trusted.
        """
        self.archive.write(self.identity)
        self.archive.write({"kind": "completion"})
        for plaintext in (b'{"kind":"identity","kind":"completion"}', b'{"value":NaN}'):
            callback = Mock(return_value=plaintext)
            with self.assertRaises(ValueError):
                verify_archive(self.archive.root, callback, self.pin, BUCKETS[0])

    def test_declared_incomplete_capture_is_rejected(self):
        """Reject incomplete terminal markers even when every request record is retained.

        Inputs:
            Complete synthetic request set with complete=false in the encrypted terminal record.
        Outputs:
            None: Asserts rejection before snapshot adaptation.
        """
        self.snapshot(complete=False)
        with self.assertRaises(ValueError):
            self.verify()

    def test_hardlink_and_directory_permissions_are_rejected(self):
        """Reject hardlinked records and directories readable by other users.

        Inputs:
            Synthetic record with an external hardlink, then an overly broad capture directory.
        Outputs:
            None: Asserts both POSIX storage-boundary failures.
        """
        self.snapshot()
        path = self.archive.root / "record-00001.cms"
        link = self.archive.root.parent / "external-link"
        os.link(path, link)
        with self.assertRaises(ValueError):
            self.verify()
        link.unlink()
        self.archive.root.chmod(0o755)
        with self.assertRaises(ValueError):
            self.verify()
        self.archive.root.chmod(0o700)

    def test_history_projection_is_recomputed_and_not_promoted_to_trial(self):
        """Bind all five history operations to raw pages and preserve original receipt times.

        Inputs:
            Complete synthetic empty history lookup pages with retained selected-bucket scope.
        Outputs:
            None: Asserts scoped history verification with no delivery or primary-trial claim.
        """
        self.archive.write(self.identity)
        self.archive.write({"kind": "scope", "phase": "development", "bucket": BUCKETS[0], "location": {"LocationConstraint": "us-east-2"}, "tags": {"TagSet": [{"Key": "Project", "Value": "aws-ai-compliance-dissertation"}]}})
        plan = history_plan(BUCKETS[0], "2026-01-01T00:00:00Z", "2026-01-01T00:30:00Z", datetime(2026, 1, 1, 1, tzinfo=timezone.utc))
        for request in plan:
            response, time = {"Events": []}, "2026-01-01T00:31:00Z"
            self.archive.write({"kind": "raw_history_page", "phase": "development", "request": request, "collector_recorded_at": time, "response": response})
            projected = scoped_events(response, request, BUCKETS[0], time)
            self.archive.write({"kind": "scoped_history_page", "phase": "development", "request": request, **projected})
        self.archive.write({"kind": "history_inspection_complete", "phase": "development", "pages_complete": True, "decoding_complete": True, "delivery_verified": False, "primary_trial_ready": False, "page_count": 5, "selected_event_count": 0, "receipts": list(self.archive.receipts)})
        result = self.verify()
        self.assertEqual(result["capture_kind"], "history_inspection")
        self.assertFalse(result["normalized"]["delivery_verified"])
        self.assertFalse(result["normalized"]["primary_trial_ready"])
        altered = copy.deepcopy(result["records"])
        altered[3]["page_sha256"] = "0" * 64
        with self.assertRaises(ValueError):
            verify_history_records(altered, BUCKETS[0])
        altered = copy.deepcopy(result["records"])
        altered[1]["bucket"] = BUCKETS[1]
        with self.assertRaises(ValueError):
            verify_history_records(altered, BUCKETS[0])


if __name__ == "__main__":
    unittest.main()
