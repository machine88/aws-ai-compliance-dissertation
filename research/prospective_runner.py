"""Development callback scheduler with pinned plans, monotonic waits and no live AWS adapter."""
import copy
import math
from datetime import datetime, timedelta
from research.catalog import canonical_sha256
from research.contracts import PROPOSAL_SHA256, WINDOW_SECONDS
from research.sampling import audit_sampling, nonnegative_seconds
from research.timing import require_sha256, utc_timestamp
from research.trials import safe_id


class CollectorAbort(RuntimeError):
    """Stop the schedule for a trusted collector's fatal scope or identity failure."""


def validate_runner_plan(plan, approved_plan_sha256):
    """Validate a source-locked runner declaration without executing any dependency.

    Inputs:
        plan: Exact development plan, collector scope pin and sampling settings.
        approved_plan_sha256: Independently trusted fingerprint of the approved plan.
    Outputs:
        tuple: Copied plan and UTC reference/cutoff/planned-closure times; no IO or callbacks.
            Invalid schemas, bounds or mismatched fingerprints raise ValueError.
    """
    keys = {"phase", "kind", "proposal_sha256", "run_id", "sampling", "max_clock_skew_seconds", "collector_scope_sha256"}
    if not isinstance(plan, dict) or set(plan) != keys or plan["phase"] != "development" or plan["kind"] != "development_sampling" or plan["proposal_sha256"] != PROPOSAL_SHA256:
        raise ValueError("Exact source-locked development runner plan required")
    safe_id(plan["run_id"])
    require_sha256(plan["collector_scope_sha256"])
    audit_sampling(plan["sampling"], [])
    skew = nonnegative_seconds(plan["max_clock_skew_seconds"])
    if skew > 60:
        raise ValueError("Development clock-skew bound must not exceed 60 seconds")
    start = utc_timestamp(plan["sampling"]["trigger_at"])
    end = start + timedelta(seconds=WINDOW_SECONDS)
    closure = utc_timestamp(plan["sampling"]["closed_at"])
    if closure > end + timedelta(seconds=WINDOW_SECONDS):
        raise ValueError("Development administrative grace must not exceed 1800 seconds")
    require_sha256(approved_plan_sha256)
    if canonical_sha256(plan) != approved_plan_sha256:
        raise ValueError("Runner plan differs from independently reviewed plan hash")
    return copy.deepcopy(plan), start, end, closure


class DevelopmentSamplingRunner:
    """Schedule bounded development collector callbacks without scores, labels or cloud clients."""

    def __init__(self, plan, approved_plan_sha256, collect, persist, wall_clock, monotonic_clock, sleeper):
        """Bind explicit trusted callbacks to an independently reviewed development plan.

        Inputs:
            plan: Exact development declaration including source, collector-scope hash and sampling settings.
            approved_plan_sha256: Independently trusted hash of the human-approved plan; not approval proof.
            collect: Silent bounded callback taking sample_id and returning status/evidence_sha256 only.
            persist: Silent encrypted-journal callback taking a record and returning its ciphertext hash.
            wall_clock: Injectable timezone-aware datetime clock for original receipt timestamps.
            monotonic_clock: Injectable finite monotonic seconds clock for scheduling/skew checks.
            sleeper: Injectable bounded sleep callback; each requested wait is at most 60 seconds.
        Outputs:
            None: Validates/copies the plan and stores callbacks; performs no collection or persistence.
            Malformed plans or mismatched approved hashes raise ValueError before callbacks run.
        """
        validated, self.start, self.end, self.closure = validate_runner_plan(plan, approved_plan_sha256)
        if not all(callable(callback) for callback in (collect, persist, wall_clock, monotonic_clock, sleeper)):
            raise ValueError("Explicit trusted collector, journal and clock callbacks required")
        self.plan, self.plan_sha256 = validated, approved_plan_sha256
        self.collect, self.persist = collect, persist
        self.wall_clock, self.monotonic_clock, self.sleeper = wall_clock, monotonic_clock, sleeper
        self.used = False
        self.journal_receipts = []

    def clocks(self):
        """Read original wall time and reject nonfinite or backward monotonic clocks.

        Inputs:
            No arguments; uses the two explicitly supplied clock callbacks and prior reading.
        Outputs:
            tuple: UTC datetime and monotonic seconds; invalid clock state raises ValueError.
        """
        wall, mono = self.wall_clock(), self.monotonic_clock()
        if not isinstance(wall, datetime) or type(mono) not in (int, float) or not math.isfinite(mono):
            raise ValueError("Aware wall clock and finite monotonic clock required")
        wall = utc_timestamp(wall.isoformat())
        if hasattr(self, "last_mono") and mono < self.last_mono:
            raise ValueError("Monotonic clock moved backward")
        self.last_mono = mono
        if hasattr(self, "reference_wall"):
            drift = abs((wall-self.reference_wall).total_seconds() - (mono-self.reference_mono))
            if drift > self.plan["max_clock_skew_seconds"]:
                raise ValueError("Wall and monotonic clocks diverged beyond reviewed bound")
        return wall, mono

    def write(self, record):
        """Persist a journal event before permitting later collector work.

        Inputs:
            record: Label-free run event sent to the trusted encrypted persistence callback.
        Outputs:
            str: Validated ciphertext receipt hash retained in memory; persistence failures propagate.
        """
        digest = self.persist(copy.deepcopy({"phase": "development", "run_id": self.plan["run_id"], **record}))
        require_sha256(digest)
        self.journal_receipts.append(digest)
        return digest

    def wait_until(self, target):
        """Wait using short sleeps while checking both clocks against the fixed run reference.

        Inputs:
            target: Aware UTC datetime for one planned acquisition or administrative closure.
        Outputs:
            datetime: Actual wall time at/after target; may sleep, never mutates the target.
        """
        target_mono = self.reference_mono + (target-self.reference_wall).total_seconds()
        while True:
            wall, mono = self.clocks()
            remaining = max((target-wall).total_seconds(), target_mono-mono)
            if remaining <= 0:
                return wall
            self.sleeper(min(remaining, 60))
            _, progressed = self.clocks()
            if progressed <= mono:
                raise ValueError("Sleeper/monotonic clock did not make progress")

    def run(self):
        """Execute the pinned schedule once and expose metadata only after administrative closure.

        Inputs:
            No arguments; uses the copied approved plan and trusted silent callbacks.
        Outputs:
            dict: Actual invocation receipts, skipped samples, timing audit and journal hashes.
                Collects no scores/labels; trigger, telemetry and formal/ML readiness stay false.
                Exceptions abort without a healthy completion marker; no retry or resume is inferred.
        """
        if self.used:
            raise ValueError("A runner instance cannot replay a schedule")
        if canonical_sha256(self.plan) != self.plan_sha256:
            raise ValueError("Pinned runner plan changed before execution")
        self.used = True
        self.reference_wall, self.reference_mono = self.clocks()
        first = self.start + timedelta(seconds=self.plan["sampling"]["samples"][0]["offset_seconds"])
        if (first-self.reference_wall).total_seconds() > WINDOW_SECONDS:
            raise ValueError("Launch must be within 1800 seconds of the first scheduled target")
        self.write({"kind": "run_opened", "plan_sha256": self.plan_sha256,
                    "collector_scope_sha256": self.plan["collector_scope_sha256"],
                    "monotonic_seconds": self.reference_mono,
                    "recorded_at": self.reference_wall.isoformat(), "trigger_verified": False})
        receipts, skipped = [], []
        for sample in self.plan["sampling"]["samples"]:
            identifier = sample["sample_id"]
            target = self.start + timedelta(seconds=sample["offset_seconds"])
            due = self.wait_until(target)
            self.write({"kind": "sample_due", "sample_id": identifier, "scheduled_at": target.isoformat(),
                        "recorded_at": due.isoformat(), "monotonic_seconds": self.last_mono})
            # Journal persistence can itself consume the permitted start lateness.
            requested, requested_mono = self.clocks()
            deadline = min(target + timedelta(seconds=self.plan["sampling"]["max_start_lateness_seconds"]), self.end)
            if requested > deadline or (sample["offset_seconds"] < 0 and requested >= self.start):
                skipped.append(identifier)
                self.write({"kind": "sample_skipped", "sample_id": identifier,
                            "reason": "start_deadline_missed", "recorded_at": requested.isoformat(), "monotonic_seconds": requested_mono})
                continue
            try:
                response = self.collect(identifier)
            except CollectorAbort:
                raise
            except Exception:
                # Do not retain exception text that could contain credentials or raw service data.
                recorded, recorded_mono = self.clocks()
                evidence = self.write({"kind": "collector_failed", "sample_id": identifier,
                                       "recorded_at": recorded.isoformat(), "reason": "collector_exception"})
                response = {"status": "error", "evidence_sha256": evidence}
            else:
                recorded, recorded_mono = self.clocks()
            if not isinstance(response, dict) or set(response) != {"status", "evidence_sha256"} or response["status"] not in ("success", "error"):
                raise ValueError("Collector must return only status and source evidence hash")
            require_sha256(response["evidence_sha256"])
            receipt = {"sample_id": identifier, "request_started_at": requested.isoformat(),
                       "recorded_at": recorded.isoformat(), "source_observed_at": None, **response}
            self.write({"kind": "sample_returned", "receipt": receipt,
                        "invocation_started_monotonic_seconds": requested_mono,
                        "invocation_recorded_monotonic_seconds": recorded_mono})
            receipts.append(receipt)
        # Actual closure is retained separately; it never extends the fixed detection cutoff.
        actual_closed = self.wait_until(self.closure)
        audit_plan = copy.deepcopy(self.plan["sampling"])
        audit_plan["closed_at"] = actual_closed.isoformat()
        audit = audit_sampling(audit_plan, receipts)
        self.write({"kind": "run_closed", "recorded_at": actual_closed.isoformat(),
                    "plan_sha256": self.plan_sha256, "audit_sha256": canonical_sha256(audit),
                    "monotonic_seconds": self.last_mono, "prior_journal_receipts": list(self.journal_receipts),
                    "acquisition_schedule_met": audit["acquisition_schedule_met"]})
        return {"version": "development-sampling-runner-v0.1", "phase": "development",
                "plan_sha256": self.plan_sha256, "planned_closed_at": self.closure.isoformat(),
                "actual_closed_at": actual_closed.isoformat(), "receipts": receipts, "skipped_samples": skipped,
                "sampling_audit": audit, "journal_receipts": list(self.journal_receipts),
                "collector_scope_sha256": self.plan["collector_scope_sha256"],
                "trigger_verified": False, "provider_delivery_verified": False, "source_freshness_verified": False,
                "paired_monitoring_validated": False, "sender_authenticated": False, "ml_ready": False,
                "formal_trial_authorized": False}
