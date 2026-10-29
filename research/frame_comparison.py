"""Offline candidate state-change counts from independently verified, separately timed frames."""
from research.catalog import canonical_sha256
from research.sampling import nonnegative_seconds
from research.state_frames import FACT_OPERATIONS, build_state_frame
from research.timing import utc_timestamp
from research.trials import safe_id


def compare_state_frames(sources, decrypt_record, recipient_sha256, bucket, cutoff_at,
                         max_acquisition_span_seconds, max_receipt_gap_seconds):
    """Compare adjacent verified frames without bridging unknown, late or oversized gaps.

    Inputs:
        sources: Ordered list of frame_id/root/archive_sha256/record_pins snapshot bindings.
        decrypt_record: Trusted authenticated decryption callback used for every archive.
        recipient_sha256: Independently trusted normalized public certificate fingerprint.
        bucket: Independently reviewed bucket shared by every source frame.
        cutoff_at: Explicit receipt cutoff supplied to each state-frame builder.
        max_acquisition_span_seconds: Explicit development acquisition-span bound per frame.
        max_receipt_gap_seconds: Explicit maximum adjacent per-fact receipt gap, zero through 1,800.
    Outputs:
        dict: Hash-bound frame reports, per-fact comparisons and a candidate delta count only
            when all local checks pass. Unknown/blocked comparisons never become zero changes.
            Makes no AWS call, file write, model fit, adaptation or ground-truth join.
            Malformed, reused or backward sources raise ValueError; ML/formal gates stay false.
    """
    limit = nonnegative_seconds(max_receipt_gap_seconds)
    nonnegative_seconds(max_acquisition_span_seconds)
    cutoff = utc_timestamp(cutoff_at)
    if not isinstance(sources, list) or not 2 <= len(sources) <= 1000:
        raise ValueError("Two through 1,000 ordered development source frames required")
    frames, identifiers, archives, records = [], set(), set(), set()
    blockers = []
    for source in sources:
        if not isinstance(source, dict) or set(source) != {"frame_id", "root", "archive_sha256", "record_pins"}:
            raise ValueError("Exact frame source bindings required; clock/fact/label overrides are forbidden")
        identifier = safe_id(source["frame_id"])
        if identifier in identifiers:
            raise ValueError("Duplicate frame identifier")
        frame = build_state_frame(source["root"], decrypt_record, recipient_sha256, bucket,
                                  source["archive_sha256"], source["record_pins"], cutoff_at,
                                  max_acquisition_span_seconds)
        pins = set(source["record_pins"].values())
        if source["archive_sha256"] in archives or pins & records:
            raise ValueError("An archive or fact record cannot be reused across frames")
        identifiers.add(identifier)
        archives.add(source["archive_sha256"])
        records.update(pins)
        if frames and frames[-1]["frame"]["acquisition_recorded_at"] is not None and frame["acquisition_started_at"] is not None:
            if utc_timestamp(frame["acquisition_started_at"]) < utc_timestamp(frames[-1]["frame"]["acquisition_recorded_at"]):
                raise ValueError("Ordered snapshot acquisitions overlap or move backward")
        frames.append({"frame_id": identifier, "frame_sha256": canonical_sha256(frame), "frame": frame})
        blockers.extend({"frame_id": identifier, "reason": reason} for reason in frame["blockers"])
    comparisons = []
    for previous, current in zip(frames, frames[1:]):
        for fact in sorted(FACT_OPERATIONS):
            before, after = previous["frame"]["facts"][fact], current["frame"]["facts"][fact]
            left, right = previous["frame"]["fact_provenance"][fact], current["frame"]["fact_provenance"][fact]
            reasons = []
            if before is None or after is None:
                reasons.append("unknown_fact")
            if any(p[key] is None for p in (left, right) for key in ("request_started_at", "collector_recorded_at")):
                reasons.append("missing_request_timing")
            gap = None
            if left["collector_recorded_at"] is not None and right["collector_recorded_at"] is not None:
                old_receipt, new_receipt = utc_timestamp(left["collector_recorded_at"]), utc_timestamp(right["collector_recorded_at"])
                gap = (new_receipt-old_receipt).total_seconds()
                if gap < 0 or (right["request_started_at"] is not None and utc_timestamp(right["request_started_at"]) < old_receipt):
                    raise ValueError("Per-fact acquisition order moves backward or overlaps")
                if gap > limit:
                    reasons.append("receipt_gap_exceeds_bound")
                if old_receipt > cutoff or new_receipt > cutoff:
                    reasons.append("received_after_cutoff")
            if any("acquisition_span_exceeds_bound" in item["frame"]["blockers"] for item in (previous, current)):
                reasons.append("frame_acquisition_span_exceeds_bound")
            # Compare only adjacent acquisitions; never skip a missing middle fact.
            comparisons.append({"previous_frame_id": previous["frame_id"], "current_frame_id": current["frame_id"],
                                "fact": fact, "before": before, "after": after,
                                "receipt_gap_seconds": gap, "changed": None if reasons else before != after,
                                "blockers": reasons})
            blockers.extend({"previous_frame_id": previous["frame_id"], "current_frame_id": current["frame_id"],
                             "fact": fact, "reason": reason} for reason in reasons)
    # Partial diagnostics are retained, but the ML component is withheld if anything is blocked.
    changed = sum(item["changed"] is True for item in comparisons)
    unchanged = sum(item["changed"] is False for item in comparisons)
    return {"version": "development-adjacent-frame-comparison-v0.1", "phase": "development",
            "frames": frames, "comparisons": comparisons, "blockers": blockers,
            "known_changed_comparisons": changed, "known_unchanged_comparisons": unchanged,
            "unresolved_comparisons": sum(item["changed"] is None for item in comparisons),
            "candidate_configuration_delta_count": changed if not blockers else None,
            "local_comparison_checks_passed": not blockers,
            "input_sha256": canonical_sha256({"frames": [{"frame_id": item["frame_id"],
                "frame_sha256": item["frame_sha256"]} for item in frames], "max_receipt_gap_seconds": limit}),
            "max_receipt_gap_seconds": limit, "atomic_snapshot_established": False,
            "source_freshness_verified": False, "provider_delivery_verified": False, "sender_authenticated": False,
            "ml_ready": False, "formal_trial_authorized": False}
