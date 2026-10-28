"""Encrypted development history inspection; never certify live event delivery or trial readiness."""
import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from research.aws_reader import ACCOUNT, REGION, BUCKETS, EncryptedArchive, check_scope, json_default, verify_identity
from research.event_history import LookupPacer, history_plan, scoped_events


def main(arguments=None, session_factory=boto3.Session, now_factory=None):
    """Preview or execute approved read-only history inspection with encrypted raw pages.

    Inputs:
        arguments: Optional CLI arguments; None reads process arguments.
        session_factory: Injectable SDK session constructor for offline tests.
        now_factory: Optional zero-argument UTC clock; None uses the current UTC time.
    Outputs:
        int: Zero when all bounded lookups finish without parse issues, otherwise one.
            Writes encrypted pages/projections/summary and public certificate only. No trial readiness.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", action="store_true")
    parser.add_argument("--execute-reviewed-read", action="store_true")
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--bucket", choices=BUCKETS, default=BUCKETS[0])
    parser.add_argument("--profile", default="dissertation-evidence-reader")
    parser.add_argument("--recipient-cert", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--openssl")
    parser.add_argument("--max-items", type=int, default=1000)
    args = parser.parse_args(arguments)
    archive = None
    try:
        current = now_factory() if now_factory else datetime.now(timezone.utc)
        plan = history_plan(args.bucket, args.start, args.end, current)
        if args.plan:
            print(json.dumps({"phase": "development", "requests": plan, "delivery_verified": False, "primary_trial_ready": False}, indent=2))
            return 0
        if not args.execute_reviewed_read or not args.output or not args.recipient_cert or not 1 <= args.max_items <= 1000:
            parser.error("Execution requires reviewed-read opt-in, new output path, public certificate and max-items 1..1000")
        archive = EncryptedArchive(args.output, args.recipient_cert, args.openssl)
        session = session_factory(profile_name=args.profile, region_name=REGION)
        config = Config(connect_timeout=5, read_timeout=15, retries={"total_max_attempts": 3, "mode": "standard"}, ignore_configured_endpoint_urls=True)
        clients = {name: session.client(name, region_name=REGION, config=config) for name in ("sts", "s3", "cloudtrail")}
        identity = clients["sts"].get_caller_identity()
        verify_identity(identity)
        archive.write({"kind": "identity", "phase": "development", "response": identity})
        owner = {"Bucket": args.bucket, "ExpectedBucketOwner": ACCOUNT}
        # Verify both bucket guards before the broader regional EventName history reads.
        location = clients["s3"].get_bucket_location(**owner)
        check_scope("get_bucket_location", location)
        tags = clients["s3"].get_bucket_tagging(**owner)
        check_scope("get_bucket_tagging", tags)
        archive.write({"kind": "scope", "phase": "development", "location": location, "tags": tags})
        cloudtrail = clients["cloudtrail"]
        pacer = LookupPacer()
        cloudtrail.meta.events.register("before-send.cloudtrail.LookupEvents", pacer.before_send)
        pages_complete, decoding_complete, page_count, selected_count = True, True, 0, 0
        for request in plan:
            try:
                pages = cloudtrail.get_paginator("lookup_events").paginate(**request["params"], PaginationConfig={"PageSize": 50, "MaxItems": args.max_items})
                for page in pages:
                    recorded = (now_factory() if now_factory else datetime.now(timezone.utc)).isoformat()
                    normalized = json.loads(json.dumps(page, default=json_default))
                    # Encrypt raw provider data before filtering; it may include other buckets' events.
                    archive.write({"kind": "raw_history_page", "phase": "development", "request": request, "collector_recorded_at": recorded, "response": normalized})
                    projected = scoped_events(normalized, request, args.bucket, recorded)
                    archive.write({"kind": "scoped_history_page", "phase": "development", "request": request, **projected})
                    page_count += 1
                    selected_count += len(projected["envelopes"])
                    decoding_complete = decoding_complete and not projected["issue_counts"]
                if pages.resume_token:
                    pages_complete = False
                    archive.write({"kind": "truncated", "request": request, "resume_token": pages.resume_token})
            except ClientError as error:
                pages_complete = False
                archive.write({"kind": "instrumentation_error", "request": request, "code": error.response.get("Error", {}).get("Code", "Unknown")})
        summary = {"kind": "history_inspection_complete", "phase": "development", "pages_complete": pages_complete,
                   "decoding_complete": decoding_complete, "delivery_verified": False, "primary_trial_ready": False,
                   "page_count": page_count, "selected_event_count": selected_count, "receipts": list(archive.receipts)}
        archive.write(summary)
        # Print counts/status only; retain requests, resource identifiers and bodies inside ciphertext.
        print(json.dumps({key: summary[key] for key in ("phase", "pages_complete", "decoding_complete", "delivery_verified", "primary_trial_ready", "page_count", "selected_event_count")}))
        return 0 if pages_complete and decoding_complete else 1
    except (ClientError, BotoCoreError, ValueError, OSError, TypeError, subprocess.SubprocessError):
        print(json.dumps({"phase": "development", "pages_complete": False, "delivery_verified": False, "error": "History inspection stopped; partial archives are not trial evidence"}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
