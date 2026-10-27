"""Require a purpose, named inputs and outputs for every maintained Python function."""
import ast
import re
from pathlib import Path


def documentation_issues(node):
    """Identify incomplete function contracts without importing or running the code.

    Inputs:
        node: Parsed Python function or asynchronous-function AST node.

    Outputs:
        list[str]: Missing purpose, input, parameter or output descriptions.
    """
    doc = ast.get_docstring(node)
    if not doc:
        return ["purpose, Inputs and Outputs docstring missing"]
    problems = []
    # Require real section content, not just empty headings that satisfy a text search.
    lines = doc.splitlines()
    for heading in ("Inputs:", "Outputs:"):
        if heading not in [line.strip() for line in lines]:
            problems.append(heading + " section missing")
    if problems:
        return problems
    input_text = doc.split("Inputs:", 1)[1].split("Outputs:", 1)[0].strip()
    output_text = doc.split("Outputs:", 1)[1].strip()
    if not lines[0].strip() or lines[0].strip() in {"Inputs:", "Outputs:"}:
        problems.append("purpose missing")
    if not input_text:
        problems.append("input explanation missing")
    if not output_text:
        problems.append("output explanation missing")
    # Every explicit argument needs its own description; self and cls are implicit state.
    arguments = node.args.posonlyargs + node.args.args + node.args.kwonlyargs
    if node.args.vararg:
        arguments.append(node.args.vararg)
    if node.args.kwarg:
        arguments.append(node.args.kwarg)
    for argument in arguments:
        if argument.arg not in {"self", "cls"} and not re.search(r"(?m)^\s*" + re.escape(argument.arg) + r":\s*\S", input_text):
            problems.append("input " + argument.arg + " missing")
    return problems


def missing_descriptions(root):
    """Find missing module descriptions and incomplete function contracts.

    Inputs:
        root: Repository root containing research, scripts and tests folders.

    Outputs:
        list[str]: File/line references and specific documentation problems.
    """
    missing = []
    for folder in ("research", "scripts", "tests"):
        for path in (root / folder).rglob("*.py"):
            # Inspect source only, keeping this check independent of scientific dependencies.
            tree = ast.parse(path.read_text())
            if not ast.get_docstring(tree):
                missing.append(f"{path.relative_to(root)}:1: module purpose missing")
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    for problem in documentation_issues(node):
                        missing.append(f"{path.relative_to(root)}:{node.lineno}: {node.name}: {problem}")
    return missing


def main():
    """Print contract violations and return a failing status when any remain.

    Inputs:
        Maintained Python source and test files beneath this repository.

    Outputs:
        int: Zero when all documentation contracts pass, otherwise one.
    """
    missing = missing_descriptions(Path(__file__).resolve().parents[1])
    if missing:
        print("Documentation needing attention:\n" + "\n".join(missing))
        return 1
    print("Every Python function explains its purpose, inputs and outputs.")
    return 0


# Convert the check result into the process status consumed by local checks and CI.
if __name__ == "__main__":
    raise SystemExit(main())
