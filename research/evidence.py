"""Offline evidence envelope. No collection, inference or cloud side effects."""
import hashlib
import json
from pathlib import Path

PARTITIONS = {"development", "pilot", "confirmatory"}

def write_evidence(root, partition, trial_id, payload, protocol_sha256):
    """Save a checksummed trial record in its phase without overwriting evidence."""
    if partition not in PARTITIONS:
        raise ValueError("invalid partition")
    if not trial_id or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for c in trial_id):
        raise ValueError("unsafe trial ID")
    if len(protocol_sha256) != 64 or any(c not in "0123456789abcdef" for c in protocol_sha256):
        raise ValueError("protocol SHA-256 required")
    # Canonical JSON keeps the payload checksum reproducible.
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    envelope = {"partition": partition, "trial_id": trial_id,
                "protocol_sha256": protocol_sha256,
                "payload_sha256": hashlib.sha256(raw).hexdigest(), "payload": payload}
    path = Path(root) / partition / (trial_id + ".json")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x") as f:
        json.dump(envelope, f, sort_keys=True, allow_nan=False)
    return path
