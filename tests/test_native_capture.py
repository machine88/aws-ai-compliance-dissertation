"""Synthetic encrypted native-wrapper tests; workers/SDK calls are mocked except timeout probes."""
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, patch
from research.archive_ingestion import verify_archive
from research.aws_reader import ACCOUNT, BUCKETS, READER_PREFIX, EncryptedArchive, read_plan
from research.catalog import canonical_sha256
from research.native_capture import (NativeSnapshotCallbacks, native_scope, validate_native_scope,
                                     bounded_worker, snapshot_fingerprint, worker_environment, READER_ROLE)
from research.native_capture import run_native_capture
from research.contracts import PROPOSAL_SHA256
from research.prospective_runner import CollectorAbort
from scripts.prospective_snapshot_worker import main as worker_main, reader_session, PROFILE


class NativeTests(unittest.TestCase):
    """Verify local crypto/source guards and process lifecycle without connecting to AWS."""

    @classmethod
    def setUpClass(cls):
        """Create an ephemeral synthetic RSA certificate for actual CMS tests.

        Inputs:
            No arguments; uses local OpenSSL and temporary test storage only.
        Outputs:
            None: Stores synthetic key/public-certificate paths, never a user recipient.
        """
        cls.temporary = tempfile.TemporaryDirectory()
        cls.base = Path(cls.temporary.name).resolve()
        cls.binary = "/opt/homebrew/opt/openssl@3/bin/openssl" if Path("/opt/homebrew/opt/openssl@3/bin/openssl").exists() else shutil.which("openssl")
        cls.key, cls.cert = cls.base / "test.key", cls.base / "public.pem"
        subprocess.run([cls.binary, "req", "-x509", "-newkey", "rsa:3072", "-nodes", "-keyout", str(cls.key),
                        "-out", str(cls.cert), "-days", "1", "-subj", "/CN=synthetic-native-test"], check=True, capture_output=True)

    @classmethod
    def tearDownClass(cls):
        """Remove the synthetic recipient and test ciphertexts.

        Inputs:
            Class-owned temporary storage only.
        Outputs:
            None: Deletes test artifacts without touching real captures or keys.
        """
        cls.temporary.cleanup()

    def setUp(self):
        """Prepare a fresh private parent and reviewable local scope.

        Inputs:
            No external input; uses the synthetic public certificate and installed test runtime.
        Outputs:
            None: Stores unexecuted native scope; makes no AWS call or credential lookup.
        """
        self.parent = Path(tempfile.mkdtemp(dir=self.base))
        self.scope = native_scope(BUCKETS[0], self.cert, self.parent / "run", self.binary, 3, 50, 1, 2)
        self.pin = canonical_sha256(self.scope)

    def decrypt(self, ciphertext):
        """Decrypt synthetic CMS bytes in memory for assertions.

        Inputs:
            ciphertext: One test-only encrypted record.
        Outputs:
            bytes: Authenticated synthetic plaintext; writes no plaintext file.
        """
        return subprocess.run([self.binary, "cms", "-decrypt", "-binary", "-inform", "DER", "-recip", str(self.cert),
                               "-inkey", str(self.key)], input=ciphertext, check=True, capture_output=True).stdout

    def fake_worker(self, command, descriptor, timeout_seconds):
        """Write an actual encrypted synthetic snapshot instead of starting any SDK worker.

        Inputs:
            command: Expected pinned Python/worker argv, retained only for validation.
            descriptor: Reviewed scope, public certificate and scheduled sample identifier.
            timeout_seconds: Expected native deadline from the reviewed scope.
        Outputs:
            str: success after writing a synthetic complete CMS archive; no AWS calls.
        """
        self.assertEqual(command[1], "-I")
        self.assertEqual(timeout_seconds, 3)
        output = Path(self.scope["output_root"]) / "samples" / descriptor["sample_id"]
        archive = EncryptedArchive(output, descriptor["certificate"], self.binary, timeout_seconds=3)
        archive.write({"kind": "identity", "phase": "development", "response": {"Account": ACCOUNT, "Arn": READER_PREFIX+"synthetic"}})
        for request in read_plan(BUCKETS[0]):
            operation = request["operation"]
            body = {"LocationConstraint": "us-east-2"} if operation == "get_bucket_location" else {}
            if operation == "get_bucket_tagging":
                body = {"TagSet": [{"Key": "Project", "Value": "aws-ai-compliance-dissertation"}]}
            if operation == "get_bucket_policy":
                body = {"Policy": '{"Statement": []}'}
            archive.write({"kind": "response", "phase": "development", "request": request,
                           "collector_recorded_at": "2026-01-01T00:01:00Z", "response": body})
        archive.write({"kind": "completion", "phase": "development", "complete": True, "receipts": list(archive.receipts)})
        return "success"

    def test_native_snapshot_and_journal_remain_encrypted_and_bound(self):
        """Validate real CMS output and exact verifier-compatible snapshot fingerprints.

        Inputs:
            Scoped native callbacks with the synthetic encrypted fake worker.
        Outputs:
            None: Asserts private encrypted output, compatible hashes and replay/invocation caps.
        """
        native = NativeSnapshotCallbacks(self.scope, self.pin, self.cert)
        with patch("research.native_capture.bounded_worker", side_effect=self.fake_worker) as worker:
            result = native.collect("sample-1")
            root = native.samples / "sample-1"
            verified = verify_archive(root, self.decrypt, self.scope["recipient_sha256"], BUCKETS[0])
            self.assertEqual(result["evidence_sha256"], verified["archive_sha256"])
            self.assertEqual(result["status"], "success")
            self.assertFalse(verified["formal_trial_authorized"])
            with self.assertRaises(CollectorAbort):
                native.collect("sample-1")
            native.collect("sample-2")
            with self.assertRaises(CollectorAbort):
                native.collect("sample-3")
            self.assertEqual(worker.call_count, 2)
        for path in native.root.rglob("*"):
            self.assertEqual(path.stat().st_mode & 0o777, 0o700 if path.is_dir() else 0o600)
        self.assertNotIn(b'"scope"', (native.journal.root / "record-00000.cms").read_bytes())
        with self.assertRaises(FileExistsError):
            NativeSnapshotCallbacks(self.scope, self.pin, self.cert)

    def test_native_runner_composes_scope_journal_and_virtual_schedule(self):
        """Rehearse the native composition with encrypted fake snapshots and virtual waits.

        Inputs:
            Exact synthetic plan/scope pins, a fake worker and virtual UTC/monotonic clocks.
        Outputs:
            None: Asserts closed report, preserved gates, encrypted final report and no real AWS calls.
        """
        origin = datetime(2026, 1, 1, tzinfo=timezone.utc)
        elapsed = [-20.0]
        def wall():
            """Return synthetic UTC time for this composition rehearsal.

            Inputs:
                No arguments; uses the test's virtual elapsed time.
            Outputs:
                datetime: Aware fake clock value, not a system-clock read.
            """
            return origin+timedelta(seconds=elapsed[0])
        def mono():
            """Return the rehearsal's synthetic monotonic time.

            Inputs:
                No arguments; reads the virtual elapsed-time fixture.
            Outputs:
                float: Fake monotonic seconds with a fixed reference offset.
            """
            return elapsed[0]+10000
        def sleep(seconds):
            """Advance the test clock without sleeping in real time.

            Inputs:
                seconds: Requested scheduling wait interval.
            Outputs:
                None: Advances virtual elapsed time only.
            """
            elapsed[0] += seconds
        plan = {"phase": "development", "kind": "development_sampling", "proposal_sha256": PROPOSAL_SHA256,
                "run_id": "synthetic-native", "collector_scope_sha256": self.pin, "max_clock_skew_seconds": 1,
                "sampling": {"phase": "development", "trigger_at": origin.isoformat(),
                    "closed_at": (origin+timedelta(seconds=1800)).isoformat(), "max_start_lateness_seconds": 1,
                    "max_response_seconds": 5, "max_anchor_age_seconds": 30,
                    "samples": [{"sample_id": "anchor", "offset_seconds": -20},
                                {"sample_id": "middle", "offset_seconds": 60}]}}
        wrong = {**plan, "collector_scope_sha256": "0"*64}
        with self.assertRaises(ValueError):
            run_native_capture(wrong, canonical_sha256(wrong), self.scope, self.pin, self.cert, wall, mono, sleep)
        self.assertFalse(Path(self.scope["output_root"]).exists())
        with patch("research.native_capture.bounded_worker", side_effect=self.fake_worker) as worker:
            result = run_native_capture(plan, canonical_sha256(plan), self.scope, self.pin, self.cert, wall, mono, sleep)
        self.assertEqual(worker.call_count, 2)
        self.assertEqual(result["report"]["actual_closed_at"], plan["sampling"]["closed_at"])
        self.assertFalse(result["report"]["trigger_verified"])
        self.assertFalse(result["report"]["ml_ready"])
        journal = Path(self.scope["output_root"]) / "journal"
        records = sorted(journal.glob("record-*.cms"))
        final = records[-1].read_bytes()
        self.assertEqual(hashlib.sha256(final).hexdigest(), result["native_report_receipt"])
        self.assertEqual(json.loads(self.decrypt(final))["kind"], "native_run_report")

    def test_timeout_and_fatal_worker_outcomes_do_not_become_success(self):
        """Preserve encrypted error evidence and stop fatal source/identity failures.

        Inputs:
            Mocked timeout and fatal worker outcomes; no subprocess or SDK is started.
        Outputs:
            None: Asserts error hashes, encrypted failure metadata and fatal abort propagation.
        """
        native = NativeSnapshotCallbacks(self.scope, self.pin, self.cert)
        with patch("research.native_capture.bounded_worker", return_value="timeout"):
            result = native.collect("sample-1")
        self.assertEqual(result["status"], "error")
        content = json.loads(self.decrypt((native.journal.root / "record-00001.cms").read_bytes()))
        self.assertEqual(content["reason"], "timeout")
        self.assertFalse(content["partial_output_retained"])
        with patch("research.native_capture.bounded_worker", return_value="fatal"):
            with self.assertRaises(CollectorAbort):
                native.collect("sample-2")

    def test_scope_changes_and_public_output_parent_fail_before_worker(self):
        """Refuse substituted code/recipient scope and broadly accessible output parents.

        Inputs:
            Tampered scope, wrong approved hash and a nonprivate synthetic parent.
        Outputs:
            None: Asserts failed local validation without any AWS/subprocess worker calls.
        """
        changed = json.loads(json.dumps(self.scope))
        changed["code_sha256"]["research/native_capture.py"] = "0"*64
        with self.assertRaises(ValueError):
            validate_native_scope(changed, canonical_sha256(changed), self.cert)
        with self.assertRaises(ValueError):
            NativeSnapshotCallbacks(self.scope, "0"*64, self.cert)
        self.parent.chmod(0o755)
        with self.assertRaises(ValueError):
            NativeSnapshotCallbacks(self.scope, self.pin, self.cert)
        self.assertFalse(Path(self.scope["output_root"]).exists())
        self.parent.chmod(0o700)

    def test_fingerprint_rejects_extra_files(self):
        """Refuse unexpected plaintext/extra files in a worker's snapshot directory.

        Inputs:
            Valid synthetic encrypted snapshot with an added empty extra file.
        Outputs:
            None: Asserts inventory validation fails rather than fingerprinting unrelated contents.
        """
        native = NativeSnapshotCallbacks(self.scope, self.pin, self.cert)
        with patch("research.native_capture.bounded_worker", side_effect=self.fake_worker):
            native.collect("sample-1")
        root = native.samples / "sample-1"
        (root / "unexpected.txt").touch(mode=0o600)
        with self.assertRaises(ValueError):
            snapshot_fingerprint(root, self.scope["recipient_sha256"])

    def test_worker_descriptor_is_strict_and_role_resolution_is_lazy(self):
        """Validate the worker contract without resolving a source profile or invoking AWS.

        Inputs:
            Prepared private native paths, a valid descriptor and mocked snapshot entry point.
        Outputs:
            None: Asserts role resolution is deferred until collector encryption preflight.
        """
        native = NativeSnapshotCallbacks(self.scope, self.pin, self.cert)
        descriptor = {"scope": self.scope, "approved_scope_sha256": self.pin,
                      "certificate": str(native.journal.cert), "sample_id": "sample-1"}
        with patch.dict(os.environ, worker_environment(), clear=True), patch("scripts.prospective_snapshot_worker.snapshot_main", return_value=0) as snapshot, patch("scripts.prospective_snapshot_worker.reader_session") as reader:
            self.assertEqual(worker_main([], io.BytesIO(json.dumps(descriptor).encode())), 0)
            reader.assert_not_called()
            factory = snapshot.call_args.kwargs["session_factory"]
            factory(PROFILE, "us-east-2")
            reader.assert_called_once()
            descriptor["expected"] = "compliant"
            self.assertEqual(worker_main([], io.BytesIO(json.dumps(descriptor).encode())), 2)

    def test_reader_profile_is_in_memory_and_source_cannot_be_root(self):
        """Exercise role metadata with SDK mocks, never credentials or real service calls.

        Inputs:
            Synthetic local-login profile metadata and mocked STS source identities.
        Outputs:
            None: Asserts isolated role core, fixed role/source settings and wrong-source refusal.
        """
        source_core, role_core = Mock(), Mock()
        source_core.get_scoped_config.return_value = {"login_session": "synthetic"}
        role_core.full_config = {"profiles": {}}
        source, role = Mock(), Mock()
        source.client.return_value.get_caller_identity.return_value = {
            "Account": ACCOUNT, "Arn": f"arn:aws:iam::{ACCOUNT}:user/martin-morales-personal"}
        make_session = Mock(side_effect=[source, role])
        self.assertIs(reader_session(make_session, Mock(side_effect=[source_core, role_core])), role)
        profile = role_core.full_config["profiles"][PROFILE]
        self.assertEqual(profile["role_arn"], READER_ROLE)
        self.assertEqual(profile["source_profile"], "dissertation")
        self.assertNotIn("aws_access_key_id", profile)
        source.client.return_value.get_caller_identity.return_value["Arn"] = f"arn:aws:iam::{ACCOUNT}:root"
        with self.assertRaises(ValueError):
            reader_session(Mock(return_value=source), Mock(return_value=source_core))
        source_core.get_scoped_config.return_value = {"credential_process": "forbidden", "login_session": "synthetic"}
        make_session = Mock()
        with self.assertRaises(ValueError):
            reader_session(make_session, Mock(return_value=source_core))
        make_session.assert_not_called()

    def test_worker_environment_drops_credential_and_python_overrides(self):
        """Remove inherited credential/endpoint/import overrides without reading or logging secrets.

        Inputs:
            Synthetic environment values, not actual AWS keys or tokens.
        Outputs:
            None: Asserts child isolation flags and absence of overrides.
        """
        with patch.dict(os.environ, {"AWS_ACCESS_KEY_ID": "synthetic-only", "AWS_CONFIG_FILE": "/unused",
                                     "AWS_ENDPOINT_URL": "https://unused.invalid", "PYTHONPATH": "/unused"}):
            env = worker_environment()
        for key in ["AWS_ACCESS_KEY_ID", "AWS_CONFIG_FILE", "AWS_ENDPOINT_URL", "PYTHONPATH"]:
            self.assertNotIn(key, env)
        self.assertEqual(env["AWS_IGNORE_CONFIGURED_ENDPOINT_URLS"], "true")
        self.assertEqual(env["AWS_EC2_METADATA_DISABLED"], "true")

    def test_real_process_group_timeout_discards_outputs(self):
        """Kill a synthetic sleeping process group; no SDK or worker capture is executed.

        Inputs:
            A local Python child that spawns a sleeping grandchild and writes its PID in test storage.
        Outputs:
            None: Asserts timeout and that the grandchild is absent or nonrunning zombie afterward.
        """
        pid_file = self.parent / "test-child.pid"
        code = ("import subprocess,sys,time; from pathlib import Path; "
                "p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(20)']); "
                "Path(sys.argv[1]).write_text(str(p.pid)); print('synthetic-hidden-output'); time.sleep(20)")
        result = bounded_worker([sys.executable, "-I", "-c", code, str(pid_file)], {}, 1)
        self.assertEqual(result, "timeout")
        self.assertTrue(pid_file.exists())
        pid = int(pid_file.read_text())
        state = subprocess.run(["ps", "-o", "stat=", "-p", str(pid)], capture_output=True, text=True).stdout.strip()
        self.assertTrue(not state or state.startswith("Z"))
