"""Offline source-bound development feature components; never promotes retrospective evidence to ML."""
from research.archive_ingestion import verify_archive
from research.catalog import canonical_sha256
from research.contracts import PROPOSAL_SHA256, WINDOW_SECONDS
from research.event_features import count_event_inputs
from research.frame_comparison import compare_state_frames
from research.sampling import nonnegative_seconds
from research.timing import require_sha256, utc_timestamp


def build_feature_bundle(history_source, frame_sources, decrypt_record, recipient_sha256,
                         bucket, window, max_acquisition_span_seconds, max_receipt_gap_seconds):
    """Join verified history diagnostics and adjacent state changes without releasing a vector.

    Inputs:
        history_source: Exact root/archive_sha256 binding for an independently pinned history capture.
        frame_sources: Ordered pinned snapshot bindings accepted by compare_state_frames.
        decrypt_record: Trusted authenticated decryption callback used for all archives.
        recipient_sha256: Independently trusted normalized public certificate fingerprint.
        bucket: Independently reviewed research bucket shared by both evidence sources.
        window: Exact development proposal_sha256/window_start/window_end/closed_at declaration.
        max_acquisition_span_seconds: Explicit per-frame development acquisition-span bound.
        max_receipt_gap_seconds: Explicit adjacent per-fact development receipt-gap bound.
    Outputs:
        dict: Seven candidate components, diagnostic audits and hash-only source provenance.
            Event components stay null when page/event timing is blocked; features always
            remains null pending independent readiness gates. No AWS call, model or file IO
            beyond local verified archive reads/decryption; no raw bodies/paths are returned.
    """
    keys = {"phase", "proposal_sha256", "window_start", "window_end", "closed_at"}
    if not isinstance(window, dict) or set(window) != keys or window["phase"] != "development" or window["proposal_sha256"] != PROPOSAL_SHA256:
        raise ValueError("Exact source-locked development window required")
    start, end, closed = [utc_timestamp(window[key]) for key in ("window_start", "window_end", "closed_at")]
    if (end-start).total_seconds() != WINDOW_SECONDS or closed < end:
        raise ValueError("Closed 1800-second feature window required")
    nonnegative_seconds(max_acquisition_span_seconds)
    nonnegative_seconds(max_receipt_gap_seconds)
    if not isinstance(history_source, dict) or set(history_source) != {"root", "archive_sha256"}:
        raise ValueError("Exact independently pinned history source required")
    require_sha256(history_source["archive_sha256"])
    history = verify_archive(history_source["root"], decrypt_record, recipient_sha256, bucket)
    if history["capture_kind"] != "history_inspection" or history["archive_sha256"] != history_source["archive_sha256"]:
        raise ValueError("Pinned history archive differs from verified source")
    interval = tuple(utc_timestamp(value) for value in history["normalized"]["interval"])
    if interval != (start, end):
        raise ValueError("History interval differs from the declared feature window")
    page_receipts = [utc_timestamp(record["collector_recorded_at"]) for record in history["records"]
                     if record.get("kind") == "raw_history_page"]
    if any(receipt > closed for receipt in page_receipts):
        raise ValueError("History pages were recorded after declared closure")
    late_pages = sum(receipt > end for receipt in page_receipts)
    event_audit = count_event_inputs(history["normalized"]["envelopes"], bucket,
                                    window["window_start"], window["window_end"], window["closed_at"])
    comparison = compare_state_frames(frame_sources, decrypt_record, recipient_sha256, bucket,
                                      window["window_end"], max_acquisition_span_seconds, max_receipt_gap_seconds)
    # Local integrity and page completion cannot establish these independent scientific gates.
    blockers = ["provider_delivery_unverified", "source_freshness_unverified", "trigger_unverified",
                "sampling_schedule_unbound", "extractor_protocol_not_frozen"]
    blockers.extend("event:" + reason for reason in event_audit["blockers"])
    if late_pages:
        blockers.append("history_pages_recorded_after_cutoff")
    if comparison["blockers"]:
        blockers.append("state_comparison_blocked")
    outside = []
    for item in comparison["frames"]:
        if any(p["collector_recorded_at"] is not None and utc_timestamp(p["collector_recorded_at"]) > closed
               for p in item["frame"]["fact_provenance"].values()):
            raise ValueError("State facts were recorded after declared closure")
        earliest = item["frame"]["acquisition_started_at"]
        if earliest is not None and utc_timestamp(earliest) < start:
            outside.append(item["frame_id"])
    if outside:
        blockers.append("state_acquisition_before_window")
    # Diagnostic zeros stay auditable; they are never imputed as complete model observations.
    components = {name: None if late_pages or event_audit["blockers"] else value
                  for name, value in event_audit["counts"].items()}
    components["configuration_delta_count"] = None if outside else comparison["candidate_configuration_delta_count"]
    return {"version": "development-verified-feature-bundle-v0.1", "phase": "development",
            "proposal_sha256": PROPOSAL_SHA256, "window": dict(window),
            "candidate_components": components, "features": None, "ml_ready": False,
            "event_audit": event_audit, "state_comparison": comparison,
            "history_archive_sha256": history_source["archive_sha256"],
            "history_page_count": len(page_receipts), "history_late_page_count": late_pages,
            "state_frames_before_window": outside, "blockers": sorted(blockers),
            "input_sha256": canonical_sha256({"history_archive_sha256": history_source["archive_sha256"],
                "state_comparison_sha256": comparison["input_sha256"], "window": window,
                "recipient_sha256": recipient_sha256, "bucket": bucket}),
            "source_freshness_verified": False, "provider_delivery_verified": False,
            "sender_authenticated": False, "formal_trial_authorized": False,
            "independent_ground_truth_used": False}
