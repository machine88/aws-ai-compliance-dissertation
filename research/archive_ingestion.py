"""Verify private encrypted capture chains through a caller-owned authenticated decryption boundary."""
import hashlib
import json
import os
import re
import stat
from research.aws_reader import verify_identity, read_plan, check_scope, OPTIONAL_ABSENCE_CODES
from research.catalog import canonical_sha256
from research.event_features import MUTATIONS
from research.event_history import scoped_events
from research.observations import normalize_snapshot
from research.timing import require_sha256


def unique_object(pairs):
    """Reject ambiguous repeated JSON keys instead of silently overwriting values.

    Inputs:
        pairs: Ordered key/value pairs supplied by the JSON parser for one object.
    Outputs:
        dict: Unique-key object; duplicate fields raise ValueError.
    """
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


def reject_constant(value):
    """Reject nonstandard nonfinite JSON numeric constants in decoded envelopes.

    Inputs:
        value: Parser spelling of NaN, Infinity or -Infinity.
    Outputs:
        None: Always raises ValueError without returning an invalid number.
    """
    raise ValueError("Nonfinite JSON value forbidden")


def private_bytes(directory_fd, name, remaining):
    """Read a bounded owned regular file through an already-open private directory.

    Inputs:
        directory_fd: Open capture-directory descriptor, avoiding path substitution.
        name: Direct child filename obtained from the verified directory listing.
        remaining: Maximum bytes that may be read without exceeding the archive limit.
    Outputs:
        bytes: File content; symlinks, hardlinks, broad permissions and concurrent changes fail.
    """
    descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory_fd)
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_uid != os.getuid() or before.st_mode & 0o077 or before.st_nlink != 1 or before.st_size > remaining:
            raise ValueError("Unsafe or oversized capture file")
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            content = stream.read(remaining + 1)
        after = os.fstat(descriptor)
        if len(content) > remaining or (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (after.st_size, after.st_mtime_ns, after.st_ctime_ns):
            raise ValueError("Capture changed during read or exceeded limit")
        return content
    finally:
        os.close(descriptor)


def verify_archive(root, decrypt_record, recipient_sha256, bucket, max_records=10000, max_bytes=67108864):
    """Verify ciphertext receipts and decoded scope without accessing private keys directly.

    Inputs:
        root: Existing POSIX capture directory owned by the current user, with private permissions.
        decrypt_record: Trusted callback accepting ciphertext bytes and returning authenticated plaintext bytes.
        recipient_sha256: Externally pinned SHA-256 of the collector's normalized public PEM certificate.
        bucket: Reviewed bucket expected independently of the archive's own declarations.
        max_records: Positive upper limit on encrypted records admitted in memory.
        max_bytes: Positive cumulative byte limit for certificate, ciphertext and decrypted plaintext.
    Outputs:
        dict: Verified in-memory records, archive fingerprint and normalized snapshot/history metadata.
            Writes no plaintext and makes no cloud call. Consistency is not sender authentication,
            provider completeness, trigger attestation, ML readiness or formal-trial authorization.
    """
    require_sha256(recipient_sha256)
    read_plan(bucket)
    if type(max_records) is not int or max_records < 1 or type(max_bytes) is not int or max_bytes < 1:
        raise ValueError("Positive ingestion limits required")
    directory = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        attributes = os.fstat(directory)
        if attributes.st_uid != os.getuid() or attributes.st_mode & 0o077:
            raise ValueError("Private owned capture directory required")
        names = os.listdir(directory)
        files = [name for name in names if re.fullmatch(r"record-\d{5,}\.cms", name)]
        files.sort(key=lambda name: int(name[7:-4]))
        if not 2 <= len(files) <= max_records or set(names) != set(files) | {"recipient-public.pem"}:
            raise ValueError("Unexpected, missing or excessive archive files")
        if files != [f"record-{index:05d}.cms" for index in range(len(files))]:
            raise ValueError("Record sequence has gaps or noncanonical names")
        certificate = private_bytes(directory, "recipient-public.pem", max_bytes)
        if b"PRIVATE KEY" in certificate or hashlib.sha256(certificate).hexdigest() != recipient_sha256:
            raise ValueError("Recipient certificate differs from trusted pin")
        used = len(certificate)
        records, receipts = [], []
        for name in files:
            ciphertext = private_bytes(directory, name, max_bytes-used)
            used += len(ciphertext)
            plaintext = decrypt_record(ciphertext)
            if not isinstance(plaintext, bytes) or len(plaintext) > max_bytes-used:
                raise ValueError("Decryption boundary returned invalid or excessive plaintext")
            used += len(plaintext)
            record = json.loads(plaintext, object_pairs_hook=unique_object, parse_constant=reject_constant)
            if not isinstance(record, dict) or ("phase" in record and record["phase"] != "development"):
                raise ValueError("Development JSON envelopes required")
            records.append(record)
            receipts.append({"file": name, "ciphertext_sha256": hashlib.sha256(ciphertext).hexdigest()})
        if set(os.listdir(directory)) != set(names):
            raise ValueError("Capture directory changed during ingestion")
    finally:
        os.close(directory)
    # The final encrypted completion record must name every predecessor, in order and by hash.
    terminal = records[-1]
    if terminal.get("phase") != "development":
        raise ValueError("Development completion marker required")
    if terminal.get("receipts") != receipts[:-1]:
        raise ValueError("Ciphertext receipt chain mismatch")
    if records[0].get("kind") != "identity" or records[0].get("phase") != "development":
        raise ValueError("Reader identity must open the archive")
    verify_identity(records[0]["response"])
    if terminal.get("kind") == "completion":
        if terminal.get("complete") is not True or any(r.get("kind") in {"truncated", "instrumentation_error"} for r in records):
            raise ValueError("Incomplete snapshot cannot enter the adapter")
        expected_requests = {canonical_sha256(request) for request in read_plan(bucket)}
        completed_requests = {canonical_sha256(record["request"]) for record in records if record.get("kind") in {"response", "absent"}}
        if completed_requests != expected_requests:
            raise ValueError("Missing or unrelated required snapshot requests")
        for record in records:
            if record.get("kind") == "absent" and record.get("code") not in OPTIONAL_ABSENCE_CODES.get(record["request"]["operation"], set()):
                raise ValueError("Unsupported absence cannot complete a capture")
        normalized = normalize_snapshot(records, bucket)
        kind = "snapshot"
    elif terminal.get("kind") == "history_inspection_complete":
        normalized = verify_history_records(records, bucket)
        kind = "history_inspection"
    else:
        raise ValueError("Unknown or missing terminal completion record")
    return {"phase": "development", "capture_kind": kind, "records": records, "normalized": normalized,
            "archive_sha256": canonical_sha256({"recipient_sha256": recipient_sha256, "receipts": receipts}),
            "sender_authenticated": False, "provider_delivery_verified": False, "formal_trial_authorized": False}


def verify_history_records(records, bucket):
    """Bind every scoped history projection to its immediately preceding retained raw page.

    Inputs:
        records: Complete decoded history-inspection envelopes with validated ciphertext receipts.
        bucket: Independently selected reviewed bucket, not inferred from event bodies.
    Outputs:
        dict: Original receipt-time event envelopes and false delivery/trial-readiness flags.
            Invalid scope, missing operation pages or rewritten projections raise ValueError.
    """
    terminal = records[-1]
    if terminal.get("pages_complete") is not True or terminal.get("decoding_complete") is not True or terminal.get("delivery_verified") is not False or terminal.get("primary_trial_ready") is not False:
        raise ValueError("Incomplete history or unsupported delivery assertion")
    if len(records) < 4 or records[1].get("kind") != "scope" or records[1].get("phase") != "development" or records[1].get("bucket") != bucket:
        raise ValueError("Explicit retained history bucket scope required")
    check_scope("get_bucket_location", records[1]["location"])
    check_scope("get_bucket_tagging", records[1]["tags"])
    pages, events, operations, interval = 0, [], set(), None
    body = records[2:-1]
    if len(body) % 2:
        raise ValueError("Unpaired raw/projection records")
    for index in range(0, len(body), 2):
        raw, projection = body[index:index+2]
        if raw.get("kind") != "raw_history_page" or raw.get("phase") != "development":
            raise ValueError("Unexpected history record")
        request = raw["request"]
        projected = scoped_events(raw["response"], request, bucket, raw["collector_recorded_at"])
        expected = {"kind": "scoped_history_page", "phase": "development", "request": request, **projected}
        if projection != expected or projected["issue_counts"]:
            raise ValueError("History projection not bound to retained raw page")
        window = (request["params"]["StartTime"], request["params"]["EndTime"])
        if interval is not None and interval != window:
            raise ValueError("Mixed history intervals")
        interval = window
        operations.add(request["params"]["LookupAttributes"][0]["AttributeValue"])
        events.extend(projected["envelopes"])
        pages += 1
    if type(terminal.get("page_count")) is not int or type(terminal.get("selected_event_count")) is not int:
        raise ValueError("Explicit integer history counts required")
    if operations != set(MUTATIONS) or terminal.get("page_count") != pages or terminal.get("selected_event_count") != len(events):
        raise ValueError("Missing operation pages or inconsistent history counts")
    return {"envelopes": events, "delivery_verified": False, "primary_trial_ready": False,
            "page_count": pages, "interval": interval}
