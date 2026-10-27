import json
import tempfile
import unittest
from research.evidence import write_evidence
from unittest.mock import patch
from scripts import preflight

class EvidenceTests(unittest.TestCase):
    """Check evidence isolation and the account guard without contacting AWS."""
    def test_partition_and_overwrite_protection(self):
        """Keep matching trial IDs in separate phases and reject repeated writes."""
        with tempfile.TemporaryDirectory() as root:
            pilot = write_evidence(root, "pilot", "trial-1", {"fixture": True}, "a" * 64)
            confirmatory = write_evidence(root, "confirmatory", "trial-1", {"fixture": True}, "a" * 64)
            self.assertNotEqual(pilot, confirmatory)
            self.assertEqual(json.loads(pilot.read_text())["partition"], "pilot")
            with self.assertRaises(FileExistsError):
                write_evidence(root, "pilot", "trial-1", {}, "a" * 64)
    def test_reject_invalid_metadata(self):
        """Reject invalid phases, unsafe trial paths and missing protocol hashes."""
        for partition, trial, sha in [("other", "x", "a"*64), ("pilot", "../x", "a"*64), ("pilot", "x", "missing")]:
            with self.assertRaises(ValueError):
                write_evidence("unused", partition, trial, {}, sha)
    def test_wrong_account_stops_inventory(self):
        """Stop after identity verification when the AWS account does not match."""
        with patch("sys.argv", ["preflight", "--profile", "fixture", "--region", "us-east-1"]), patch.object(preflight, "aws", return_value={"Account": "000000000000"}) as mock:
            with self.assertRaises(SystemExit):
                preflight.main()
            self.assertEqual(mock.call_count, 1)
