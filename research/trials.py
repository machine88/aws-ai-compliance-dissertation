"""Offline paired prediction storage; ground truth joins only after both records exist."""
import json
from pathlib import Path
from research.catalog import ROLES, canonical_sha256
from research.evidence import PARTITIONS
from research.contracts import FACTS

MONITORS = {"baseline", "ai"}
OUTCOMES = {"compliant", "noncompliant", "unknown", "instrument_failure"}



def safe_id(value):
    """Reject identifiers that could escape their evidence directory."""
    if not isinstance(value, str) or not value or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for c in value):
        raise ValueError("unsafe evidence identifier")
    return value


def monitor_input(resource_id, observed_facts):
    """Expose only pseudonymous resources and allowlisted observed technical facts."""
    safe_id(resource_id)
    if not observed_facts or set(observed_facts) - FACTS:
        raise ValueError("unknown or label-bearing input field")
    if any(type(value) is not bool for value in observed_facts.values()):
        raise ValueError("observed facts must be booleans, not nested metadata")
    return {"resource_id": resource_id, "observed_facts": dict(observed_facts)}


def write_prediction(root, phase, learning_role, trial_id, family_id, monitor,
                     outcome, provenance, protocol_sha256):
    """Persist one immutable monitor decision in orthogonal phase/learning partitions."""
    # Formal-run authorization will be integrated with the frozen catalog controller.
    if phase != "development":
        raise ValueError("pilot and confirmatory prediction writing is not enabled yet")
    if phase not in PARTITIONS or learning_role not in ROLES or monitor not in MONITORS:
        raise ValueError("invalid phase, learning role or monitor")
    if outcome not in OUTCOMES:
        raise ValueError("unknown results must remain explicit")
    for identifier in (trial_id, family_id):
        safe_id(identifier)
    if len(protocol_sha256) != 64 or any(c not in "0123456789abcdef" for c in protocol_sha256):
        raise ValueError("protocol hash required")
    required = {"model_version", "feature_version", "mapping_version", "adaptation_version", "observation_sha256", "scenario_id"}
    if set(provenance) != required or any(not isinstance(v, str) or not v for v in provenance.values()):
        raise ValueError("complete, label-free version provenance required")
    safe_id(provenance["scenario_id"])
    observation_hash = provenance["observation_sha256"]
    if len(observation_hash) != 64 or any(c not in "0123456789abcdef" for c in observation_hash):
        raise ValueError("paired observation hash required")
    payload = {"phase": phase, "learning_role": learning_role, "trial_id": trial_id,
               "family_id": family_id, "monitor": monitor, "outcome": outcome,
               "provenance": provenance, "protocol_sha256": protocol_sha256}
    envelope = {"payload": payload, "payload_sha256": canonical_sha256(payload)}
    path = Path(root) / phase / learning_role / trial_id / f"{monitor}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x") as stream:
        json.dump(envelope, stream, sort_keys=True, allow_nan=False)
    return path


def join_for_evaluation(root, phase, learning_role, trial_id, truth_entry):
    """Join labels after matching predictions persist; preserve unresolved unknowns."""
    if phase not in PARTITIONS or learning_role not in ROLES:
        raise ValueError("invalid evaluation partition")
    safe_id(trial_id)
    records = {}
    for monitor in sorted(MONITORS):
        path = Path(root) / phase / learning_role / trial_id / f"{monitor}.json"
        envelope = json.loads(path.read_text())
        record = envelope["payload"]
        if canonical_sha256(record) != envelope["payload_sha256"]:
            raise ValueError("prediction checksum mismatch")
        if (record["phase"], record["learning_role"], record["trial_id"], record["monitor"]) != (phase, learning_role, trial_id, monitor):
            raise ValueError("prediction path and metadata disagree")
        records[monitor] = record
    first, second = records["ai"], records["baseline"]
    for key in ("family_id", "protocol_sha256"):
        if first[key] != second[key]:
            raise ValueError("unpaired prediction metadata")
    for key in ("observation_sha256", "scenario_id"):
        if first["provenance"][key] != second["provenance"][key]:
            raise ValueError("monitors did not receive the same scenario observations")
    if truth_entry["scenario_id"] != first["provenance"]["scenario_id"] or truth_entry["expected"] not in {"compliant", "noncompliant"}:
        raise ValueError("ground truth does not match persisted scenario")
    return {"phase": phase, "learning_role": learning_role, "trial_id": trial_id,
            "expected": truth_entry["expected"], "predictions": records,
            "metric_policy": "unknown-compliant denominator and baseline fusion unresolved"}
