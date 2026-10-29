"""Synthetic acquisition tests; no AWS access or measured research outcomes."""
import copy
import unittest
from datetime import datetime, timedelta, timezone
from research.sampling import audit_sampling


class SamplingTests(unittest.TestCase):
    """Keep late/missing acquisitions distinct from valid scientific evidence."""

    def stamp(self, seconds):
        """Create a synthetic timezone-aware clock.

        Inputs:
            seconds: Offset from the fixed synthetic trigger.
        Outputs:
            str: UTC timestamp; performs no IO.
        """
        return (datetime(2026, 1, 1, tzinfo=timezone.utc)+timedelta(seconds=seconds)).isoformat()

    def setUp(self):
        """Prepare illustrative tolerances, not approved live protocol settings.

        Inputs:
            No external inputs; fixtures use invented clocks and placeholder hashes.
        Outputs:
            None: Retains a development plan and receipts on this test instance.
        """
        self.plan = {"phase": "development", "trigger_at": self.stamp(0), "closed_at": self.stamp(1860),
                     "max_start_lateness_seconds": 2, "max_response_seconds": 5,
                     "max_anchor_age_seconds": 30,
                     "samples": [{"sample_id": "anchor", "offset_seconds": -20},
                                 {"sample_id": "middle", "offset_seconds": 900},
                                 {"sample_id": "last", "offset_seconds": 1790}]}
        self.receipts = [{"sample_id": name, "request_started_at": self.stamp(offset),
                          "recorded_at": self.stamp(offset+2), "source_observed_at": None,
                          "status": "success", "evidence_sha256": "a"*64}
                         for name, offset in [("anchor", -20), ("middle", 900), ("last", 1790)]]

    def test_acquisition_does_not_claim_readiness(self):
        """Accept realistic response delays without inventing exact source observations.

        Inputs:
            Synthetic plan/receipts from setUp.
        Outputs:
            None: Asserts acquisition success, input preservation and closed readiness gates.
        """
        original = copy.deepcopy((self.plan, self.receipts))
        result = audit_sampling(self.plan, list(reversed(self.receipts)))
        self.assertTrue(result["acquisition_schedule_met"])
        for field in ["ml_ready", "source_freshness_verified", "provider_delivery_verified", "formal_trial_authorized"]:
            self.assertFalse(result[field])
        self.assertIsNone(result["samples"][0]["receipt"]["source_observed_at"])
        self.assertEqual((self.plan, self.receipts), original)
        self.assertEqual(result["plan_sha256"], audit_sampling(self.plan, [])['plan_sha256'])
        changed = copy.deepcopy(self.plan)
        changed["max_response_seconds"] += 1
        self.assertNotEqual(result["plan_sha256"], audit_sampling(changed, [])['plan_sha256'])

    def test_missing_and_failed_samples_remain_blockers(self):
        """Retain failed request evidence and list missing scheduled acquisitions.

        Inputs:
            Synthetic receipts with one absent sample and one explicit error.
        Outputs:
            None: Asserts both blockers; no absence is relabeled compliant.
        """
        self.receipts.pop()
        self.receipts[1]["status"] = "error"
        result = audit_sampling(self.plan, self.receipts)
        self.assertEqual({b["reason"] for b in result["blockers"]}, {"request_error", "missing_receipt"})

    def test_late_receipt_never_extends_horizon(self):
        """Keep late evidence at administrative closure without backdating it.

        Inputs:
            Last receipt occurs after the fixed horizon but before closure.
        Outputs:
            None: Asserts lateness and retained original receipt time.
        """
        self.receipts[-1]["recorded_at"] = self.stamp(1801)
        result = audit_sampling(self.plan, self.receipts)
        self.assertIn("received_after_horizon", result["samples"][-1]["blockers"])
        self.assertEqual(result["samples"][-1]["receipt"]["recorded_at"], self.stamp(1801))
        self.assertFalse(result["acquisition_schedule_met"])

    def test_anchor_and_schedule_tolerances(self):
        """Exercise exact tolerance edges and distinguish stale/late anchors.

        Inputs:
            Independent synthetic clock edits for anchor age and request timing.
        Outputs:
            None: Asserts inclusive bounds and each out-of-bound blocker.
        """
        cases = [("request_started_at", 899, "request_before_target"),
                 ("request_started_at", 903, "late_request_start"),
                 ("recorded_at", 906, "slow_response")]
        for field, offset, reason in cases:
            receipts = copy.deepcopy(self.receipts)
            receipts[1][field] = self.stamp(offset)
            if field == "request_started_at":
                receipts[1]["recorded_at"] = self.stamp(offset+1)
            self.assertIn(reason, audit_sampling(self.plan, receipts)["samples"][1]["blockers"])
        self.plan["max_anchor_age_seconds"] = 18
        self.assertTrue(audit_sampling(self.plan, self.receipts)["acquisition_schedule_met"])
        self.plan["max_anchor_age_seconds"] = 17
        self.assertIn("anchor_too_old", audit_sampling(self.plan, self.receipts)["samples"][0]["blockers"])
        self.receipts[0]["recorded_at"] = self.stamp(1)
        self.assertIn("anchor_received_after_trigger", audit_sampling(self.plan, self.receipts)["samples"][0]["blockers"])

    def test_untrusted_source_clock_is_retained(self):
        """Retain a stale supplied source clock without promoting it to fresh evidence.

        Inputs:
            Synthetic source timestamp much older than the request.
        Outputs:
            None: Asserts its measured age and unverified freshness.
        """
        self.receipts[1]["source_observed_at"] = self.stamp(100)
        result = audit_sampling(self.plan, self.receipts)
        self.assertEqual(result["samples"][1]["source_age_at_receipt_seconds"], 802)
        self.assertFalse(result["source_freshness_verified"])

    def test_invalid_clocks_and_duplicate_receipts_fail(self):
        """Refuse ambiguous receipts rather than selecting a favorable observation.

        Inputs:
            Separate malformed duplicate, future, inverted and naive clock cases.
        Outputs:
            None: Asserts ValueError for each malformed receipt set.
        """
        duplicate = copy.deepcopy(self.receipts[:2])
        duplicate.append(copy.deepcopy(duplicate[0]))
        with self.assertRaises(ValueError):
            audit_sampling(self.plan, duplicate)
        for field, value in [("recorded_at", self.stamp(1900)),
                             ("recorded_at", self.stamp(899)),
                             ("source_observed_at", self.stamp(903)),
                             ("request_started_at", "2026-01-01T00:15:00")]:
            receipts = copy.deepcopy(self.receipts)
            receipts[1][field] = value
            with self.assertRaises(ValueError):
                audit_sampling(self.plan, receipts)

    def test_protocol_schema_and_formal_use_fail(self):
        """Reject implicit defaults, labels, formal phases and malformed schedules.

        Inputs:
            Independent malformed plan variants and unexpected receipt fields.
        Outputs:
            None: Asserts fail-closed validation before an acquisition report is returned.
        """
        for key, value in [("phase", "pilot"), ("phase", "confirmatory"),
                           ("max_response_seconds", True), ("max_anchor_age_seconds", -1),
                           ("max_start_lateness_seconds", float("nan")),
                           ("closed_at", self.stamp(1799)), ("expected", "compliant")]:
            plan = copy.deepcopy(self.plan)
            plan[key] = value
            with self.assertRaises(ValueError):
                audit_sampling(plan, self.receipts)
        for offsets in [[0, 900, 1790], [-20, -10, 900], [-20, 900, 900], [-20, 1801, 1802]]:
            plan = copy.deepcopy(self.plan)
            for item, offset in zip(plan["samples"], offsets):
                item["offset_seconds"] = offset
            with self.assertRaises(ValueError):
                audit_sampling(plan, [])
        self.receipts[0]["expected"] = "compliant"
        with self.assertRaises(ValueError):
            audit_sampling(self.plan, self.receipts)
