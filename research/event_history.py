"""Bounded CloudTrail history plans and scoped decoding; lookup completion is not delivery proof."""
import json
import time
from datetime import timedelta
from research.aws_reader import ACCOUNT, REGION, BUCKETS
from research.catalog import canonical_sha256
from research.contracts import WINDOW_SECONDS
from research.event_features import MUTATIONS
from research.timing import utc_timestamp


def history_plan(bucket, start, end, now):
    """Plan five read-only EventName lookups in one closed development interval.

    Inputs:
        bucket: One reviewed research bucket used for client-side attribution.
        start: ISO timezone-aware interval start.
        end: ISO timezone-aware inclusive interval end, exactly 1800 seconds later.
        now: Timezone-aware current UTC datetime for future/90-day boundary checks.
    Outputs:
        list[dict]: Fixed CloudTrail LookupEvents requests; no AWS call or credential lookup.
    """
    first, last = utc_timestamp(start), utc_timestamp(end)
    if bucket not in BUCKETS or now.tzinfo is None or (last-first).total_seconds() != WINDOW_SECONDS:
        raise ValueError("Reviewed bucket and fixed timezone-aware interval required")
    if last > now or first < now - timedelta(days=90):
        raise ValueError("History requires a closed interval within the last 90 days")
    # EventName is the only server filter; bucket/account/source are rechecked after retrieval.
    return [{"service": "cloudtrail", "operation": "lookup_events", "params": {
        "LookupAttributes": [{"AttributeKey": "EventName", "AttributeValue": operation}],
        "StartTime": first.isoformat(), "EndTime": last.isoformat()}}
        for operation in sorted(MUTATIONS)]


class LookupPacer:
    """Space local HTTP attempts below the documented per-account/region lookup limit."""

    def __init__(self, clock=time.monotonic, sleeper=time.sleep):
        """Initialize the sequential request pacer without starting any network activity.

        Inputs:
            clock: Injectable monotonic clock, independent of wall-clock adjustments.
            sleeper: Injectable sleep function used to space HTTP attempts.
        Outputs:
            None: Stores a process-local next-attempt time; does not coordinate other processes.
        """
        self.clock, self.sleeper, self.next_at = clock, sleeper, 0.0

    def before_send(self, request, **kwargs):
        """Pace SDK HTTP sends, including retries, without inspecting signed requests.

        Inputs:
            request: SDK event argument; never inspected, saved or logged.
            kwargs: Other SDK hook arguments; ignored without logging.
        Outputs:
            None: May sleep, then updates the next permitted HTTP-attempt time.
        """
        delay = self.next_at - self.clock()
        if delay > 0:
            self.sleeper(delay)
        self.next_at = self.clock() + 0.55


def scoped_events(page, request, bucket, recorded_at):
    """Project attributable provider events while retaining malformed-input issue counts.

    Inputs:
        page: JSON-compatible LookupEvents response, already retained privately by the caller.
        request: One exact maintained lookup request containing operation and interval.
        bucket: Selected reviewed bucket, independently rechecked against requestParameters.
        recorded_at: Actual UTC collector receipt time, never provider event time.
    Outputs:
        dict: Scoped event envelopes, ignored/issue counts and raw-page hash; no evidence writes.
    """
    if bucket not in BUCKETS:
        raise ValueError("Unreviewed bucket")
    receipt_time = utc_timestamp(recorded_at)
    parameters = request["params"]
    if request not in history_plan(bucket, parameters["StartTime"], parameters["EndTime"], receipt_time):
        raise ValueError("Request does not match the bounded history plan")
    operation = parameters["LookupAttributes"][0]["AttributeValue"]
    if operation not in MUTATIONS:
        raise ValueError("Unreviewed mutation operation")
    start, end = utc_timestamp(parameters["StartTime"]), utc_timestamp(parameters["EndTime"])
    selected, ignored, issues = [], {}, {}
    for wrapper in page.get("Events", []):
        reason = None
        try:
            event = json.loads(wrapper["CloudTrailEvent"])
            if not isinstance(event, dict):
                raise ValueError("Event must be an object")
            if not isinstance(event.get("eventID"), str) or not event["eventID"] or wrapper.get("EventId") != event["eventID"] or wrapper.get("EventName") != operation or event.get("eventName") != operation:
                raise ValueError("Outer and inner provider identity mismatch")
            if event.get("eventSource") != "s3.amazonaws.com" or event.get("recipientAccountId") != ACCOUNT or event.get("awsRegion") != REGION:
                reason = "other_service_account_or_region"
            else:
                attribution = event.get("requestParameters")
                if not isinstance(attribution, dict) or not isinstance(attribution.get("bucketName"), str):
                    raise ValueError("Missing bucket attribution")
                if attribution["bucketName"] != bucket:
                    reason = "other_bucket"
                elif not start <= utc_timestamp(event["eventTime"]) <= end:
                    reason = "outside_source_window"
            if reason:
                ignored[reason] = ignored.get(reason, 0) + 1
            else:
                selected.append({"event": event, "collector_recorded_at": recorded_at})
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            # Preserve the raw encrypted page outside this helper; never silently create an empty stream.
            issues["malformed_or_unattributable_event"] = issues.get("malformed_or_unattributable_event", 0) + 1
    return {"envelopes": selected, "ignored_counts": ignored, "issue_counts": issues,
            "page_sha256": canonical_sha256(page)}
