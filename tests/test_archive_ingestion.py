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
from research.capture_sampling import audit_snapshot_sampling
from research.catalog import canonical_sha256
from research.state_frames import build_state_frame, FACT_OPERATIONS
from research.frame_comparison import compare_state_frames
from research.aws_reader import ACCOUNT, BUCKETS, READER_PREFIX, EncryptedArchive, read_plan
from research.event_history import history_plan, scoped_events
from datetime import datetime, timedelta, timezone


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

    def snapshot(self, omit=None, complete=True, timing=None, record_updates=None):
        """Write a complete synthetic snapshot request ledger and its encrypted terminal chain.

        Inputs:
            omit: Optional operation to omit for missing-source tests.
            complete: Explicit completion declaration to place in the terminal marker.
            timing: Optional synthetic request/receipt clocks; None retains the legacy fixture.
            record_updates: Optional per-operation envelope edits for synthetic provenance tests.
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
            self.archive.write({"kind": "response", "phase": "development", "request": request,
                                "collector_recorded_at": "2026-01-01T00:31:00Z", **(timing or {}),
                                "response": body, **(record_updates or {}).get(operation, {})})
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

    def frame_fixture(self, changes=None, legacy=False, offset_seconds=0):
        """Create a genuine synthetic archive with six facts from three separate read intervals.

        Inputs:
            changes: Optional per-operation edits to the synthetic response/timing envelope.
            legacy: When true omit request-start clocks without reconstructing them.
            offset_seconds: Whole synthetic time shift applied to the three fixture intervals.
        Outputs:
            dict: Keyword arguments for build_state_frame; writes only synthetic ciphertext.
        """
        policy = {"Statement": [{"Effect": "Deny", "Principal": "*", "Action": "s3:*",
                  "Resource": [f"arn:aws:s3:::{BUCKETS[0]}", f"arn:aws:s3:::{BUCKETS[0]}/*"],
                  "Condition": {"Bool": {"aws:SecureTransport": "false"}}}]}
        bodies = {"get_public_access_block": {"PublicAccessBlockConfiguration": {
                     "BlockPublicAcls": True, "IgnorePublicAcls": True,
                     "BlockPublicPolicy": True, "RestrictPublicBuckets": True}},
                  "get_bucket_versioning": {"Status": "Enabled"},
                  "get_bucket_policy": {"Policy": json.dumps(policy)}}
        updates = {}
        for operation, offset in [("get_public_access_block", 10), ("get_bucket_versioning", 20), ("get_bucket_policy", 30)]:
            start = datetime(2026, 1, 1, tzinfo=timezone.utc)+timedelta(seconds=offset_seconds+offset)
            updates[operation] = {"response": bodies[operation],
                                  "collector_recorded_at": (start+timedelta(seconds=2)).isoformat().replace("+00:00", "Z")}
            if not legacy:
                updates[operation]["request_started_at"] = start.isoformat().replace("+00:00", "Z")
            updates[operation].update((changes or {}).get(operation, {}))
        self.snapshot(record_updates=updates)
        verified = self.verify()
        pins = {r["request"]["operation"]: canonical_sha256(r) for r in verified["records"]
                if r.get("request", {}).get("operation") in set(FACT_OPERATIONS.values())}
        return {"root": self.archive.root, "decrypt_record": self.decrypt, "recipient_sha256": self.pin,
                "bucket": BUCKETS[0], "archive_sha256": verified["archive_sha256"], "record_pins": pins,
                "cutoff_at": (datetime(2026, 1, 1, tzinfo=timezone.utc)+timedelta(seconds=offset_seconds+32)).isoformat(),
                "max_acquisition_span_seconds": 22}

    def comparison_fixture(self, middle_changes=None, legacy_middle=False):
        """Prepare three independently encrypted snapshots at separate synthetic acquisitions.

        Inputs:
            middle_changes: Optional per-operation edits for the middle frame only.
            legacy_middle: Whether the middle archive omits request-start clocks.
        Outputs:
            dict: Keyword arguments for compare_state_frames; writes only test ciphertext.
        """
        sources = []
        for index, offset in enumerate((0, 100, 200)):
            if sources:
                self.setUp()
            arguments = self.frame_fixture(changes=middle_changes if index == 1 else None,
                                           legacy=legacy_middle and index == 1, offset_seconds=offset)
            sources.append({"frame_id": f"frame-{index}", "root": arguments["root"],
                            "archive_sha256": arguments["archive_sha256"], "record_pins": arguments["record_pins"]})
        return {"sources": sources, "decrypt_record": self.decrypt, "recipient_sha256": self.pin,
                "bucket": BUCKETS[0], "cutoff_at": "2026-01-01T00:03:52Z",
                "max_acquisition_span_seconds": 22, "max_receipt_gap_seconds": 100}

    def test_adjacent_frame_changes_and_restoration_are_counted(self):
        """Count changed booleans across adjacent acquisitions, including a captured reversal.

        Inputs:
            Synthetic versioning true/false/true sequence with exact 100-second receipt gaps.
        Outputs:
            None: Asserts two candidate changes, preserved hashes, bounded timing and no ML release.
        """
        arguments = self.comparison_fixture(middle_changes={"get_bucket_versioning": {"response": {"Status": "Suspended"}}})
        result = compare_state_frames(**arguments)
        self.assertEqual(result["candidate_configuration_delta_count"], 2)
        self.assertEqual(result["known_changed_comparisons"], 2)
        self.assertEqual(result["known_unchanged_comparisons"], 10)
        self.assertEqual(result["unresolved_comparisons"], 0)
        self.assertTrue(result["local_comparison_checks_passed"])
        self.assertEqual(len(result["frames"]), 3)
        self.assertTrue(all(item["receipt_gap_seconds"] == 100 for item in result["comparisons"]))
        self.assertNotIn('"root"', json.dumps(result))
        self.assertNotIn('"response"', json.dumps(result))
        for key in ["ml_ready", "formal_trial_authorized", "source_freshness_verified", "provider_delivery_verified", "sender_authenticated"]:
            self.assertFalse(result[key])

    def test_unknown_middle_is_not_bridged_or_imputed(self):
        """Keep unknown intermediate facts unresolved on both adjacent comparisons.

        Inputs:
            Synthetic middle public-access response without any of its four flags.
        Outputs:
            None: Asserts eight unresolved comparisons and no candidate count, despite known endpoints.
        """
        result = compare_state_frames(**self.comparison_fixture(middle_changes={"get_public_access_block": {"response": {}}}))
        self.assertIsNone(result["candidate_configuration_delta_count"])
        self.assertEqual(result["unresolved_comparisons"], 8)
        self.assertEqual(result["known_unchanged_comparisons"], 4)
        self.assertEqual(result["known_changed_comparisons"], 0)
        self.assertTrue(all(item["changed"] is None for item in result["comparisons"] if item["fact"] == "block_public_acls"))

    def test_frame_comparison_gaps_lateness_and_legacy_stay_blocked(self):
        """Withhold candidate counts for excessive gaps, late facts and missing request clocks.

        Inputs:
            Synthetic middle legacy frame, stricter receipt gap and earlier cutoff variants.
        Outputs:
            None: Asserts explicit blockers and no zero-imputation into the candidate feature.
        """
        arguments = self.comparison_fixture(legacy_middle=True)
        legacy = compare_state_frames(**arguments)
        self.assertIsNone(legacy["candidate_configuration_delta_count"])
        self.assertEqual(legacy["unresolved_comparisons"], 12)
        self.assertTrue(any(b["reason"] == "missing_request_timing" for b in legacy["blockers"]))
        arguments["max_receipt_gap_seconds"] = 99
        gap = compare_state_frames(**arguments)
        self.assertTrue(any(b["reason"] == "receipt_gap_exceeds_bound" for b in gap["blockers"]))
        arguments["cutoff_at"] = "2026-01-01T00:03:51Z"
        late = compare_state_frames(**arguments)
        self.assertTrue(any(b["reason"] == "received_after_cutoff" for b in late["blockers"]))
        self.assertIsNone(late["candidate_configuration_delta_count"])
        self.assertNotEqual(legacy["input_sha256"], gap["input_sha256"])

    def test_frame_comparison_rejects_reordering_reuse_and_overrides(self):
        """Refuse reordered/reused snapshots and caller-supplied facts or expected labels.

        Inputs:
            Independent mutations of valid encrypted source bindings and timing bounds.
        Outputs:
            None: Asserts fail-closed validation before producing a comparison report.
        """
        arguments = self.comparison_fixture()
        quiet = compare_state_frames(**arguments)
        self.assertEqual(quiet["candidate_configuration_delta_count"], 0)
        self.assertTrue(quiet["local_comparison_checks_passed"])
        gap = compare_state_frames(**{**arguments, "max_receipt_gap_seconds": 99})
        self.assertIsNone(gap["candidate_configuration_delta_count"])
        self.assertEqual(gap["unresolved_comparisons"], 12)
        span = compare_state_frames(**{**arguments, "max_acquisition_span_seconds": 21})
        self.assertIsNone(span["candidate_configuration_delta_count"])
        self.assertTrue(any(b["reason"] == "frame_acquisition_span_exceeds_bound" for b in span["blockers"]))
        for changes in [{"sources": list(reversed(arguments["sources"]))},
                        {"sources": [arguments["sources"][0], {**arguments["sources"][0], "frame_id": "reused"}]},
                        {"sources": [{**arguments["sources"][0], "expected": "compliant"}, arguments["sources"][1]]},
                        {"max_receipt_gap_seconds": True}, {"max_receipt_gap_seconds": -1},
                        {"sources": arguments["sources"][:1]}]:
            with self.assertRaises(ValueError):
                compare_state_frames(**{**arguments, **changes})

    def test_state_frame_retains_per_fact_intervals(self):
        """Combine six known facts while keeping three independent source intervals visible.

        Inputs:
            Synthetic archive with sequential 10–12, 20–22 and 30–32 second acquisitions.
        Outputs:
            None: Asserts exact inclusive span/cutoff, six facts and closed atomic/ML gates.
        """
        arguments = self.frame_fixture()
        result = build_state_frame(**arguments)
        self.assertTrue(result["all_facts_known"])
        self.assertTrue(result["frame_checks_passed"])
        self.assertEqual(len(result["facts"]), 6)
        self.assertTrue(all(result["facts"].values()))
        self.assertEqual(result["acquisition_span_seconds"], 22)
        self.assertNotEqual(result["fact_provenance"]["tls_deny_present"]["request_started_at"],
                            result["fact_provenance"]["block_public_acls"]["request_started_at"])
        for record in result["fact_provenance"].values():
            self.assertIsNone(record["source_observed_at"])
        for key in ["atomic_snapshot_established", "source_freshness_verified", "ml_ready",
                    "formal_trial_authorized", "provider_delivery_verified", "sender_authenticated"]:
            self.assertFalse(result[key])
        self.assertNotIn("observed_at", result)
        self.assertNotIn('"response"', json.dumps(result))

    def test_frame_limits_and_unknown_facts_stay_visible(self):
        """Retain unknown flags and span/cutoff failures instead of imputing compliant values.

        Inputs:
            Partial synthetic public-access configuration and stricter caller timing limits.
        Outputs:
            None: Asserts unknown values, explicit blockers and changed binding fingerprint.
        """
        arguments = self.frame_fixture(changes={"get_public_access_block": {"response": {
            "PublicAccessBlockConfiguration": {"BlockPublicAcls": True}}}})
        original = build_state_frame(**arguments)
        arguments["max_acquisition_span_seconds"] = 21
        arguments["cutoff_at"] = "2026-01-01T00:00:31Z"
        result = build_state_frame(**arguments)
        self.assertIsNone(result["facts"]["ignore_public_acls"])
        self.assertFalse(result["all_facts_known"])
        self.assertIn("unknown_fact:ignore_public_acls", result["blockers"])
        self.assertIn("acquisition_span_exceeds_bound", result["blockers"])
        self.assertIn("received_after_cutoff:get_bucket_policy", result["blockers"])
        self.assertNotEqual(original["binding_sha256"], result["binding_sha256"])

    def test_legacy_frame_has_no_invented_acquisition_bounds(self):
        """Keep known facts from an older archive but leave aggregate timing unavailable.

        Inputs:
            Synthetic legacy snapshot with receipt times and no request-start clocks.
        Outputs:
            None: Asserts facts remain known while timing and ML readiness remain blocked.
        """
        result = build_state_frame(**self.frame_fixture(legacy=True))
        self.assertTrue(result["all_facts_known"])
        self.assertFalse(result["frame_checks_passed"])
        self.assertIsNone(result["acquisition_started_at"])
        self.assertIsNone(result["acquisition_recorded_at"])
        self.assertIsNone(result["acquisition_span_seconds"])
        self.assertEqual(len(result["blockers"]), 3)

    def test_frame_pins_and_serial_clock_order_fail_closed(self):
        """Refuse substituted bindings, extra label fields and impossible serial timing.

        Inputs:
            Independent argument edits and an encrypted overlapping-request fixture.
        Outputs:
            None: Asserts malformed bindings/clocks fail before producing a frame.
        """
        arguments = self.frame_fixture()
        for changes in [{"archive_sha256": "0"*64}, {"max_acquisition_span_seconds": True},
                        {"cutoff_at": "2026-01-01T00:00:32"},
                        {"record_pins": {**arguments["record_pins"], "expected": "compliant"}},
                        {"record_pins": {**arguments["record_pins"], "get_bucket_policy": "0"*64}}]:
            with self.assertRaises(ValueError):
                build_state_frame(**{**arguments, **changes})
        self.setUp()
        overlap = self.frame_fixture(changes={"get_bucket_versioning": {
            "request_started_at": "2026-01-01T00:00:11Z"}})
        with self.assertRaises(ValueError):
            build_state_frame(**overlap)

    def sampling_fixture(self, legacy=False):
        """Encrypt two independently timed synthetic snapshots and bind one S3 request.

        Inputs:
            legacy: When true omit request clocks from the anchor to model an old archive.
        Outputs:
            tuple: Synthetic plan, source bindings and selected request hash; writes test ciphertext.
        """
        plan = {"phase": "development", "trigger_at": "2026-01-01T00:01:00Z",
                "closed_at": "2026-01-01T00:32:00Z", "max_start_lateness_seconds": 1,
                "max_response_seconds": 5, "max_anchor_age_seconds": 30,
                "samples": [{"sample_id": "anchor", "offset_seconds": -20},
                            {"sample_id": "window", "offset_seconds": 60}]}
        sources = []
        for sample_id, started, recorded in [("anchor", "00:00:40Z", "00:00:42Z"),
                                             ("window", "00:02:00Z", "00:02:02Z")]:
            if sources:
                self.setUp()
            timing = {"collector_recorded_at": "2026-01-01T"+recorded}
            if not legacy or sample_id != "anchor":
                timing["request_started_at"] = "2026-01-01T"+started
            self.snapshot(timing=timing)
            verified = self.verify()
            record = next(r for r in verified["records"] if r.get("request", {}).get("operation") == "get_public_access_block")
            sources.append({"sample_id": sample_id, "root": self.archive.root,
                            "archive_sha256": verified["archive_sha256"], "record_sha256": canonical_sha256(record)})
        return plan, sources, canonical_sha256(record["request"])

    def test_verified_archives_feed_sampling_without_raw_exports(self):
        """Use genuine CMS chains to verify selected record clocks and output minimization.

        Inputs:
            Two independent encrypted synthetic snapshots and explicit external source bindings.
        Outputs:
            None: Asserts timing success, preserved clocks and false readiness/authentication flags.
        """
        plan, sources, request_hash = self.sampling_fixture()
        result = audit_snapshot_sampling(plan, sources, self.decrypt, self.pin, BUCKETS[0], request_hash)
        self.assertTrue(result["sampling"]["acquisition_schedule_met"])
        self.assertEqual(result["sampling"]["samples"][0]["receipt"]["recorded_at"], "2026-01-01T00:00:42Z")
        self.assertIsNone(result["sampling"]["samples"][0]["receipt"]["source_observed_at"])
        encoded = json.dumps(result)
        self.assertNotIn('"root"', encoded)
        self.assertNotIn('"response"', encoded)
        for key in ["ml_ready", "formal_trial_authorized", "provider_delivery_verified", "sender_authenticated"]:
            self.assertFalse(result[key])

    def test_legacy_capture_clocks_are_not_invented(self):
        """Keep an old valid archive usable for observation but blocked for request timing.

        Inputs:
            A valid encrypted anchor snapshot without request_started_at.
        Outputs:
            None: Asserts explicit timing blocker and missing sampling receipt, not guessed clocks.
        """
        plan, sources, request_hash = self.sampling_fixture(legacy=True)
        result = audit_snapshot_sampling(plan, sources, self.decrypt, self.pin, BUCKETS[0], request_hash)
        self.assertEqual(result["capture_timing_blockers"], [{"sample_id": "anchor", "reason": "capture_request_timing_unavailable"}])
        self.assertIsNone(result["sampling"]["samples"][0]["receipt"])
        self.assertFalse(result["sampling"]["acquisition_schedule_met"])

    def test_source_binding_changes_and_reuse_fail(self):
        """Refuse substituted records, archives, scopes, reused receipts and clock overrides.

        Inputs:
            Separate mutations of valid synthetic source bindings and selected request hash.
        Outputs:
            None: Asserts fail-closed validation for every substituted binding.
        """
        plan, sources, request_hash = self.sampling_fixture()
        for field, value in [("archive_sha256", "0"*64), ("record_sha256", "0"*64),
                             ("sample_id", "unscheduled"), ("request_started_at", "2026-01-01T00:00:40Z")]:
            changed = copy.deepcopy(sources)
            changed[0][field] = value
            with self.assertRaises(ValueError):
                audit_snapshot_sampling(plan, changed, self.decrypt, self.pin, BUCKETS[0], request_hash)
        reused = [sources[0], {**sources[0], "sample_id": "window"}]
        with self.assertRaises(ValueError):
            audit_snapshot_sampling(plan, reused, self.decrypt, self.pin, BUCKETS[0], request_hash)
        wrong_request = canonical_sha256(read_plan(BUCKETS[0])[0])
        with self.assertRaises(ValueError):
            audit_snapshot_sampling(plan, sources, self.decrypt, self.pin, BUCKETS[0], wrong_request)
        paginated = next(r for r in read_plan(BUCKETS[0]) if r["paginated"])
        with self.assertRaises(ValueError):
            audit_snapshot_sampling(plan, sources, self.decrypt, self.pin, BUCKETS[0], canonical_sha256(paginated))

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
