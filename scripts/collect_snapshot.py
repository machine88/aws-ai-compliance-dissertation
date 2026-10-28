"""Capture an encrypted development snapshot; never enable monitoring or classify results."""
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
from research.aws_reader import BUCKETS, REGION, EncryptedArchive, check_scope, read_plan, verify_identity

from research.aws_reader import OPTIONAL_ABSENCE_CODES as ABSENCE_CODES


def main(arguments=None, session_factory=boto3.Session):
    """Run bounded reads with encrypted records and fail-closed prerequisite checks.

    Inputs:
        arguments: Optional CLI argument list; None uses process arguments.
        session_factory: Injectable SDK session constructor for offline stub tests.
    Outputs:
        int: Zero for a complete snapshot/plan, one for failure or truncation. Writes only
            ciphertext and public-certificate files; prints counts/status without raw evidence.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", action="store_true")
    parser.add_argument("--bucket", choices=BUCKETS, default=BUCKETS[0])
    parser.add_argument("--profile", default="dissertation-evidence-reader")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--recipient-cert", type=Path)
    parser.add_argument("--openssl")
    parser.add_argument("--max-items", type=int, default=1000)
    parser.add_argument("--max-pages", type=int, default=20)
    args = parser.parse_args(arguments)
    plan = read_plan(args.bucket)
    if args.plan:
        print(json.dumps({"phase": "development", "region": REGION, "requests": plan}, indent=2))
        return 0
    if not args.output or not args.recipient_cert or not 1 <= args.max_items <= 1000 or not 1 <= args.max_pages <= 20:
        parser.error("Live reads require a new output directory, public recipient certificate and max-items 1..1000/max-pages 1..20")
    archive = None
    try:
        # Validate local encryption before acquiring a session or issuing any cloud request.
        archive = EncryptedArchive(args.output, args.recipient_cert, args.openssl)
        session = session_factory(profile_name=args.profile, region_name=REGION)
        config = Config(connect_timeout=5, read_timeout=15, retries={"total_max_attempts": 3, "mode": "standard"}, ignore_configured_endpoint_urls=True)
        clients = {name: session.client(name, region_name=REGION, config=config) for name in ("sts", "s3", "config", "securityhub", "cloudtrail")}
        identity = clients["sts"].get_caller_identity()
        verify_identity(identity)
        archive.write({"kind": "identity", "phase": "development", "response": identity})
        complete = True
        for request in plan:
            operation = request["operation"]
            client = clients[request["service"]]
            try:
                # SDK pagination retains every returned page up to the explicit capture bound.
                if request["paginated"]:
                    pages = client.get_paginator(operation).paginate(**request["params"], PaginationConfig={"MaxItems": args.max_items})
                else:
                    pages = [getattr(client, operation)(**request["params"])]
                query_pages, capped = 0, False
                for response in pages:
                    query_pages += 1
                    archive.write({"kind": "response", "phase": "development", "request": request, "collector_recorded_at": datetime.now(timezone.utc), "response": response})
                    check_scope(operation, response)
                    # Bound empty continuation pages as well as returned item counts.
                    if request["paginated"] and query_pages >= args.max_pages and response.get("NextToken"):
                        complete, capped = False, True
                        archive.write({"kind": "truncated", "request": request, "reason": "page_cap", "next_token": response["NextToken"]})
                        break
                if request["paginated"] and not capped and pages.resume_token:
                    complete = False
                    archive.write({"kind": "truncated", "request": request, "resume_token": pages.resume_token})
            except ClientError as error:
                code = error.response.get("Error", {}).get("Code", "Unknown")
                absent = code in ABSENCE_CODES.get(operation, set())
                archive.write({"kind": "absent" if absent else "instrumentation_error", "request": request, "code": code})
                complete = complete and absent
                # Guard errors stop resource reads instead of turning an unauthorized scope into data.
                if operation in {"get_bucket_location", "get_bucket_tagging"}:
                    raise ValueError("Resource scope could not be verified") from None
        archive.write({"kind": "completion", "phase": "development", "complete": complete, "receipts": list(archive.receipts)})
        print(json.dumps({"phase": "development", "complete": complete, "encrypted_records": len(archive.receipts)}))
        return 0 if complete else 1
    except (ClientError, BotoCoreError, ValueError, OSError, subprocess.SubprocessError, TypeError):
        # Keep partial ciphertext, avoid logging service bodies, paths or credential errors.
        print(json.dumps({"phase": "development", "complete": False, "error": "Snapshot stopped; verify reader identity, scope, encryption and connectivity"}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
