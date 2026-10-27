"""Offline paired prediction storage; ground truth joins only after both records exist."""
import json
from pathlib import Path
from research.catalog import ROLES, canonical_sha256
from research.evidence import PARTITIONS
from research.contracts import FACTS

MONITORS = {"baseline", "ai"}
OUTCOMES = {"compliant", "noncompliant", "unknown", "instrument_failure"}



def safe_id(value):
    """Reject identifiers that could escape their evidence directory.

    Inputs:
        value: Candidate evidence identifier to check for unsafe path characters.

    Outputs:
        str: Validated identifier, or ValueError when unsafe.
    """
    if not isinstance(value, str) or not value or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for c in value):
        raise ValueError("unsafe evidence identifier")
    return value


def monitor_input(resource_id, observed_facts):
    """Expose only pseudonymous resources and allowlisted observed technical facts.

    Inputs:
        resource_id: Pseudonymous identifier without account or resource secrets.
        observed_facts: Allowlisted boolean facts collected from resource state.

    Outputs:
        dict: Pseudonymous resource ID and allowlisted observed facts, without labels.
    """
    safe_id(resource_id)
    # Reject fields outside the observation allowlist, including expected answers or nested labels.
    if not observed_facts or set(observed_facts) - FACTS:
        raise ValueError("unknown or label-bearing input field")
    if any(type(value) is not bool for value in observed_facts.values()):
        raise ValueError("observed facts must be booleans, not nested metadata")
    return {"resource_id": resource_id, "observed_facts": dict(observed_facts)}


def write_prediction(root, phase, learning_role, trial_id, family_id, monitor,
                     outcome, provenance, protocol_sha256, context=None):
    """Persist one immutable monitor decision in orthogonal phase/learning partitions.

    Inputs:
        root: Root directory for repository files or private evidence.
        phase: Experimental phase, separate from the learning role.
        learning_role: Training, validation/adaptation or held-out assignment.
        trial_id: Unique safe identifier for the paired trial.
        family_id: Identifier linking related scenario variants.
        monitor: Prediction source: baseline or ai.
        outcome: Explicit compliant, noncompliant, unknown or instrumentation-failure result.
        provenance: Scenario, model, feature, mapping, adaptation and observation versions.
        protocol_sha256: SHA-256 of the governing protocol.
        context: Optional catalog, assignment and predeclared answer-key hashes binding the pair to its design.

    Outputs:
        Path: New immutable checksummed prediction file in its phase/learning partition.
    """
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
    # Require all component versions so a stored decision can be traced back to its implementation.
    required = {"model_version", "feature_version", "mapping_version", "adaptation_version", "observation_sha256", "scenario_id"}
    if set(provenance) != required or any(not isinstance(v, str) or not v for v in provenance.values()):
        raise ValueError("complete, label-free version provenance required")
    safe_id(provenance["scenario_id"])
    observation_hash = provenance["observation_sha256"]
    if len(observation_hash) != 64 or any(c not in "0123456789abcdef" for c in observation_hash):
        raise ValueError("paired observation hash required")
    # Keep experiment phase and learning role as separate fields instead of conflating pilot and training.
    payload = {"phase": phase, "learning_role": learning_role, "trial_id": trial_id,
               "family_id": family_id, "monitor": monitor, "outcome": outcome,
               "provenance": provenance, "protocol_sha256": protocol_sha256}
    # Controller-managed pairs retain their design identity without exposing expected labels.
    if context is not None:
        if not isinstance(context, dict) or set(context) != {"catalog_sha256", "assignments_sha256", "ground_truth_sha256"}:
            raise ValueError("complete catalog, assignment and answer-key fingerprint context required")
        if any(not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value) for value in context.values()):
            raise ValueError("design context must contain SHA-256 hashes")
        payload["context"] = dict(context)
    envelope = {"payload": payload, "payload_sha256": canonical_sha256(payload)}
    path = Path(root) / phase / learning_role / trial_id / f"{monitor}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation prevents a later prediction from replacing an earlier determination.
    with path.open("x") as stream:
        json.dump(envelope, stream, sort_keys=True, allow_nan=False)
    return path


def join_for_evaluation(root, phase, learning_role, trial_id, truth_entry):
    """Join labels after matching predictions persist; preserve unresolved unknowns.

    Inputs:
        root: Root directory for repository files or private evidence.
        phase: Experimental phase, separate from the learning role.
        learning_role: Training, validation/adaptation or held-out assignment.
        trial_id: Unique safe identifier for the paired trial.
        truth_entry: Expected label and matching scenario ID, used only after outputs persist.

    Outputs:
        dict: Paired persisted predictions joined with the expected answer; unknowns remain explicit.
    """
    if phase not in PARTITIONS or learning_role not in ROLES:
        raise ValueError("invalid evaluation partition")
    safe_id(trial_id)
    # Load both monitor outputs before making the expected answer available to evaluation.
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
    # Require the same scenario and evidence to make the comparison genuinely paired.
    first, second = records["ai"], records["baseline"]
    if first.get("context") != second.get("context"):
        raise ValueError("monitors use different catalog or assignment context")
    for key in ("family_id", "protocol_sha256"):
        if first[key] != second[key]:
            raise ValueError("unpaired prediction metadata")
    for key in ("observation_sha256", "scenario_id"):
        if first["provenance"][key] != second["provenance"][key]:
            raise ValueError("monitors did not receive the same scenario observations")
    # Reject another scenario's answer key and preserve unknown outputs for later prespecified analysis.
    if truth_entry["scenario_id"] != first["provenance"]["scenario_id"] or truth_entry["expected"] not in {"compliant", "noncompliant"}:
        raise ValueError("ground truth does not match persisted scenario")
    return {"phase": phase, "learning_role": learning_role, "trial_id": trial_id,
            "expected": truth_entry["expected"], "predictions": records,
            "metric_policy": "unknown-compliant denominator and baseline fusion unresolved"}
