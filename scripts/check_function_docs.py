"""Enforce the project's concise function-description convention."""
import ast
from pathlib import Path


def missing_descriptions(root):
    """Find Python functions without docstrings in maintained source and test folders."""
    missing = []
    for folder in ("research", "scripts", "tests"):
        for path in (root / folder).rglob("*.py"):
            for node in ast.walk(ast.parse(path.read_text())):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not ast.get_docstring(node):
                    missing.append(f"{path.relative_to(root)}:{node.lineno}: {node.name}")
    return missing


def main():
    """Report undocumented functions and return a failing status when any remain."""
    missing = missing_descriptions(Path(__file__).resolve().parents[1])
    if missing:
        print("Functions needing a brief description:\n" + "\n".join(missing))
        return 1
    print("Every Python function has a description.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
