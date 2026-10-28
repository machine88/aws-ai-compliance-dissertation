"""Expand fixed collector requests into analysis-only SDK calls for IAM Policy Autopilot."""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from research.aws_reader import BUCKETS, read_plan


def expanded_source():
    """Expose runtime-dispatched operations to deterministic static policy analysis.

    Inputs:
        No arguments; reads the maintained fixed plans for both approved buckets.
    Outputs:
        str: Analysis-only Python source with explicit SDK calls; never executes it.
    """
    lines = ['"""Static-analysis input only. Do not execute: contains live read calls."""', 'import boto3', 'sts = boto3.client("sts")', 'sts.get_caller_identity()']
    for service in ("s3", "config", "securityhub", "cloudtrail"):
        lines.append(f'{service} = boto3.client({service!r})')
    # Expand pagination targets as direct API calls; continuation does not change IAM actions.
    seen = set()
    for bucket in BUCKETS:
        for request in read_plan(bucket):
            call = f'{request["service"]}.{request["operation"]}(**{request["params"]!r})'
            if call not in seen:
                lines.append(call)
                seen.add(call)
    return "\n".join(lines) + "\n"


def main(arguments=None):
    """Write a new analysis input without opening AWS sessions or overwriting files.

    Inputs:
        arguments: Optional CLI arguments; None uses process arguments, requiring --output.
    Outputs:
        int: Zero after an exclusive source-file write; no credentials or AWS calls.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(arguments)
    with args.output.open("x") as stream:
        stream.write(expanded_source())
    return 0


if __name__ == "__main__":
    sys.exit(main())
