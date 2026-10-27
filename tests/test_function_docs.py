"""Regression checks for the required purpose/input/output documentation format."""
import ast
import unittest
from scripts.check_function_docs import documentation_issues


class DocumentationTests(unittest.TestCase):
    """Exercise valid and incomplete contracts using source strings only."""

    def test_description_alone_is_insufficient(self):
        """Reject the old convention that explained purpose but omitted the interface.

        Inputs:
            A synthetic function with only a one-line purpose docstring.

        Outputs:
            None: Assertions require both missing section warnings.
        """
        node = ast.parse('def example(value):\n    """Return a value."""\n    return value').body[0]
        issues = documentation_issues(node)
        self.assertIn("Inputs: section missing", issues)
        self.assertIn("Outputs: section missing", issues)

    def test_every_argument_needs_an_explanation(self):
        """Require names for positional, keyword-only and variable-length inputs.

        Inputs:
            A synthetic function whose contract describes only one of four inputs.

        Outputs:
            None: Assertions require warnings for every undocumented argument.
        """
        source = 'def example(value, *items, option=True, **settings):\n    """Return a value.\n\n    Inputs:\n        value: Given value.\n\n    Outputs:\n        object: The given value.\n    """\n    return value'
        issues = documentation_issues(ast.parse(source).body[0])
        self.assertEqual(set(issues), {"input items missing", "input option missing", "input settings missing"})

    def test_complete_contract_and_no_argument_contract_pass(self):
        """Accept concise complete interfaces, including a function with no arguments.

        Inputs:
            Two synthetic source functions with documented inputs and outputs.

        Outputs:
            None: Assertions require an empty issue list for both functions.
        """
        for signature, explanation in [("value", "value: Given value."), ("", "None; uses a constant fixture.")]:
            source = f'def example({signature}):\n    """Describe the operation.\n\n    Inputs:\n        {explanation}\n\n    Outputs:\n        int: Constant fixture value.\n    """\n    return 1'
            self.assertEqual(documentation_issues(ast.parse(source).body[0]), [])
