"""Offline decision table for a future sandbox versioning runner; performs no AWS IO."""
from dataclasses import dataclass, replace

from research.sandbox_readiness import BUCKET


@dataclass(frozen=True)
class RecoveryState:
    """Immutable development state; counters describe requested actions, not cloud success."""
    phase: str = "ready"
    mutation_attempts: int = 0
    restoration_attempts: int = 0


def next_recovery_action(state, event, bucket=BUCKET):
    """Select the next bounded action from an explicitly supplied development event.

    Inputs:
        state: RecoveryState from this planner's previous transition, initially the default.
        event: Fixed event name supplied by a future trusted runner after retaining evidence.
        bucket: Exact dedicated sandbox name; no other target is accepted.
    Outputs:
        tuple: New immutable state and action string. No IO, cloud calls, persistence or
            authorization occurs. Invalid transitions raise ValueError. Recovery is verified
            only by a caller-supplied restoration_verified event; this is not source proof.
    """
    if bucket != BUCKET or not isinstance(state, RecoveryState):
        raise ValueError("Exact sandbox and recovery state required")
    # Reject fabricated counters and phases instead of permitting unsafe retry resets.
    if (type(state.mutation_attempts) is not int or state.mutation_attempts not in (0, 1)
            or type(state.restoration_attempts) is not int
            or not 0 <= state.restoration_attempts <= 3):
        raise ValueError("Invalid attempt counters")
    phase = state.phase
    if phase == "ready":
        if state != RecoveryState() or event != "preflight_retained":
            raise ValueError("Retained approved preflight required")
        return replace(state, phase="mutation_pending", mutation_attempts=1), "request_suspended_once"
    if phase not in {"mutation_pending", "observing", "restoring", "recovered", "manual_recovery"} or state.mutation_attempts != 1:
        raise ValueError("Invalid recovery phase")
    if (phase in {"mutation_pending", "observing"} and state.restoration_attempts != 0
            or phase in {"restoring", "recovered", "manual_recovery"} and state.restoration_attempts == 0):
        raise ValueError("Phase and recovery counters disagree")
    # No mutation retry exists, including when the first response is ambiguous.
    if phase == "mutation_pending" and event == "independent_suspended_receipt":
        return replace(state, phase="observing"), "observe_fixed_window"
    recovery_events = {"write_response_only", "ambiguous_mutation", "error", "deadline", "cancel"}
    if phase == "observing":
        recovery_events = {"window_closed", "error", "deadline", "cancel"}
    if phase in {"mutation_pending", "observing"} and event in recovery_events:
        return replace(state, phase="restoring", restoration_attempts=1), "request_enabled"
    if phase == "restoring":
        if event == "restoration_verified":
            return replace(state, phase="recovered"), "retain_recovery_audit"
        if event in {"restoration_failed", "restoration_ambiguous"}:
            if state.restoration_attempts < 3:
                return replace(state, restoration_attempts=state.restoration_attempts + 1), "request_enabled"
            return replace(state, phase="manual_recovery"), "block_reuse_and_escalate"
        if event in {"deadline", "cancel"}:
            return replace(state, phase="manual_recovery"), "block_reuse_and_escalate"
    raise ValueError("Event is invalid for the current recovery phase")
