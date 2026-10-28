"""Verify the analysis-only policy input exactly covers the collector's dynamic read plan."""
import ast
import unittest
from research.aws_reader import BUCKETS, read_plan
from scripts.export_reader_policy_input import expanded_source


class PolicyInputTests(unittest.TestCase):
    """Keep static IAM analysis aligned with actual collector requests."""

    def test_expansion_covers_all_requests(self):
        """Compare parsed explicit SDK calls with both fixed runtime plans.

        Inputs:
            Maintained read plans and generated source text; no SDK execution.
        Outputs:
            None: Asserts operation/parameter parity and exactly one identity call.
        """
        tree = ast.parse(expanded_source())
        calls = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name) and node.func.value.id != "boto3":
                params = ast.literal_eval(node.keywords[0].value) if node.keywords else {}
                calls.append((node.func.value.id, node.func.attr, repr(params)))
        expected = {("sts", "get_caller_identity", repr({}))}
        for bucket in BUCKETS:
            expected.update((r["service"], r["operation"], repr(r["params"])) for r in read_plan(bucket))
        self.assertEqual(set(calls), expected)
        self.assertEqual(len(calls), len(expected))

    def test_named_config_context(self):
        """Ensure context requests do not enumerate unrelated recorder/channel names.

        Inputs:
            Fixed read plan for the telemetry bucket.
        Outputs:
            None: Asserts explicit research names on all Config describe requests.
        """
        for request in read_plan(BUCKETS[0]):
            if request["service"] == "config" and request["operation"].startswith("describe_"):
                self.assertEqual(list(request["params"].values()), [["dissertation-research"]])


if __name__ == "__main__":
    unittest.main()
