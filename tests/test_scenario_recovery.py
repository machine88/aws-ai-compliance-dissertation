"""Synthetic recovery decision tests; no credentials, AWS calls or study observations."""
import unittest
from research.scenario_recovery import RecoveryState, next_recovery_action


class ScenarioRecoveryTests(unittest.TestCase):
    """Exercise uncertain writes, bounded retries and terminal reuse protection."""

    def test_normal_observation_then_verified_recovery(self):
        """Check the successful path preserves one mutation and requires recovery proof.

        Inputs:
            self: Test instance; no external inputs.
        Outputs:
            None; asserts the ordered actions and immutable initial state.
        """
        initial = RecoveryState()
        state, action = next_recovery_action(initial, "preflight_retained")
        self.assertEqual(action, "request_suspended_once")
        state, action = next_recovery_action(state, "independent_suspended_receipt")
        self.assertEqual(action, "observe_fixed_window")
        state, action = next_recovery_action(state, "window_closed")
        self.assertEqual(action, "request_enabled")
        state, action = next_recovery_action(state, "restoration_verified")
        self.assertEqual((state.phase, action), ("recovered", "retain_recovery_audit"))
        self.assertEqual(initial.mutation_attempts, 0)
        with self.assertRaises(ValueError):
            next_recovery_action(state, "preflight_retained")

    def test_uncertain_mutation_never_retries_suspension(self):
        """Route every uncertain mutation outcome to restoration, bounded at three requests.

        Inputs:
            self: Test instance; no external inputs.
        Outputs:
            None; asserts conservative recovery and terminal manual intervention.
        """
        for event in ("write_response_only", "ambiguous_mutation", "error", "deadline", "cancel"):
            state, _ = next_recovery_action(RecoveryState(), "preflight_retained")
            state, action = next_recovery_action(state, event)
            self.assertEqual(action, "request_enabled")
            for _ in range(3):
                state, action = next_recovery_action(state, "restoration_ambiguous")
            self.assertEqual((state.restoration_attempts, state.mutation_attempts), (3, 1))
            self.assertEqual(action, "block_reuse_and_escalate")
            with self.assertRaises(ValueError):
                next_recovery_action(state, "restoration_verified")

    def test_rejects_wrong_target_invalid_state_and_unverified_trigger(self):
        """Reject scope changes, impossible counters and skipped trigger/preflight transitions.

        Inputs:
            self: Test instance; no external inputs.
        Outputs:
            None; asserts invalid inputs fail closed.
        """
        with self.assertRaises(ValueError):
            next_recovery_action(RecoveryState(), "preflight_retained", "unrelated-bucket")
        for state, event in ((RecoveryState(), "independent_suspended_receipt"),
                             (RecoveryState("observing", 0), "window_closed"),
                             (RecoveryState("restoring", 1, 0), "restoration_verified"),
                             (RecoveryState("ready", True), "preflight_retained")):
            with self.assertRaises(ValueError):
                next_recovery_action(state, event)
