"""Synthetic relative-plan resolution tests; no capture, clock wait or AWS connection."""
import copy
import unittest
from datetime import timedelta
from research.capture_template import resolve_native_plan
from research.catalog import canonical_sha256
from research.contracts import PROPOSAL_SHA256
from research.timing import utc_timestamp


class TemplateTests(unittest.TestCase):
    """Keep human-approved offsets fixed while deriving actual timestamps before collection."""

    def setUp(self):
        """Prepare an illustrative development template, not an approved live capture.

        Inputs:
            No external input; uses synthetic scope identity and timing settings.
        Outputs:
            None: Retains fixture metadata without reading a system clock.
        """
        self.template = {"phase": "development", "kind": "development_native_template",
                         "proposal_sha256": PROPOSAL_SHA256, "run_id": "synthetic-template",
                         "collector_scope_sha256": "a"*64, "max_clock_skew_seconds": 1,
                         "reference_delay_seconds": 180, "administrative_grace_seconds": 30,
                         "max_start_lateness_seconds": 5, "max_response_seconds": 90,
                         "max_anchor_age_seconds": 180,
                         "samples": [{"sample_id": "anchor", "offset_seconds": -120},
                                     {"sample_id": "early", "offset_seconds": 60},
                                     {"sample_id": "late", "offset_seconds": 1740}]}

    def test_resolution_preserves_reviewed_offsets_and_fixed_horizon(self):
        """Derive times deterministically without silently approving a new template or trigger.

        Inputs:
            Fixed fixture and explicit launch timestamp with a timezone offset.
        Outputs:
            None: Asserts exact delays/horizon, reproducibility, copied inputs and false trigger flag.
        """
        original = copy.deepcopy(self.template)
        resolved = resolve_native_plan(self.template, canonical_sha256(self.template), "2026-01-01T00:00:00Z")
        repeated = resolve_native_plan(self.template, canonical_sha256(self.template), "2026-01-01T00:00:00Z")
        self.assertEqual(resolved, repeated)
        trigger = utc_timestamp(resolved["plan"]["sampling"]["trigger_at"])
        self.assertEqual(trigger-utc_timestamp(resolved["reference_at"]), timedelta(seconds=180))
        self.assertEqual(utc_timestamp(resolved["plan"]["sampling"]["closed_at"])-trigger, timedelta(seconds=1830))
        self.assertEqual(resolved["plan"]["sampling"]["samples"], self.template["samples"])
        self.assertFalse(resolved["trigger_verified"])
        resolved["plan"]["sampling"]["samples"][0]["sample_id"] = "edited-copy"
        self.assertEqual(self.template, original)

    def test_changed_or_unbounded_template_is_refused(self):
        """Reject changed approved offsets, formal phases, labels and invalid anchor launch timing.

        Inputs:
            Independent malformed variants of the synthetic reviewed template.
        Outputs:
            None: Asserts validation failure before any resolved run can be used.
        """
        with self.assertRaises(ValueError):
            resolve_native_plan(self.template, "0"*64, "2026-01-01T00:00:00Z")
        for key, value in [("phase", "pilot"), ("expected", "compliant"),
                           ("reference_delay_seconds", 0), ("administrative_grace_seconds", 1801),
                           ("reference_delay_seconds", True)]:
            changed = {**self.template, key: value}
            with self.assertRaises(ValueError):
                resolve_native_plan(changed, canonical_sha256(changed), "2026-01-01T00:00:00Z")
