"""Resolve an independently approved relative development schedule without choosing from outcomes."""
import copy
from datetime import timedelta
from research.catalog import canonical_sha256
from research.contracts import PROPOSAL_SHA256, WINDOW_SECONDS
from research.prospective_runner import validate_runner_plan
from research.sampling import nonnegative_seconds
from research.timing import require_sha256, utc_timestamp


def resolve_native_plan(template, approved_template_sha256, reference_at):
    """Bind fixed reviewed offsets to one actual launch reference before any collection.

    Inputs:
        template: Exact development native template with scope, offsets and explicit timing bounds.
        approved_template_sha256: Independently trusted hash of the human-approved relative template.
        reference_at: Actual timezone-aware launch-reference timestamp from the trusted driver.
    Outputs:
        dict: Template/reference identity, resolved runner plan and plan hash for private pre-run retention.
            Makes no IO or AWS call, selects no outcomes, and does not verify a scenario trigger.
            Changed templates, extra labels, invalid bounds or already-due anchor rules fail.
    """
    keys = {"phase", "kind", "proposal_sha256", "run_id", "collector_scope_sha256", "samples",
            "max_clock_skew_seconds", "reference_delay_seconds", "administrative_grace_seconds",
            "max_start_lateness_seconds", "max_response_seconds", "max_anchor_age_seconds"}
    require_sha256(approved_template_sha256)
    if not isinstance(template, dict) or set(template) != keys or template["phase"] != "development" or template["kind"] != "development_native_template" or template["proposal_sha256"] != PROPOSAL_SHA256:
        raise ValueError("Exact source-locked development template required")
    if canonical_sha256(template) != approved_template_sha256:
        raise ValueError("Relative capture template differs from independent approval")
    reference = utc_timestamp(reference_at)
    delay = nonnegative_seconds(template["reference_delay_seconds"])
    grace = nonnegative_seconds(template["administrative_grace_seconds"])
    trigger = reference+timedelta(seconds=delay)
    plan = {key: template[key] for key in ("phase", "proposal_sha256", "run_id", "collector_scope_sha256", "max_clock_skew_seconds")}
    plan["kind"] = "development_sampling"
    plan["sampling"] = {"phase": "development", "trigger_at": trigger.isoformat(),
                        "closed_at": (trigger+timedelta(seconds=WINDOW_SECONDS+grace)).isoformat(),
                        "samples": copy.deepcopy(template["samples"]),
                        **{key: template[key] for key in ("max_start_lateness_seconds", "max_response_seconds", "max_anchor_age_seconds")}}
    digest = canonical_sha256(plan)
    validate_runner_plan(plan, digest)
    lead = delay+plan["sampling"]["samples"][0]["offset_seconds"]
    if not 0 < lead <= WINDOW_SECONDS:
        raise ValueError("Reviewed template must leave a bounded future anchor target")
    return {"template_sha256": approved_template_sha256, "reference_at": reference.isoformat(),
            "plan": plan, "plan_sha256": digest, "trigger_verified": False}
