"""Print planning examples using the retained Ohio public-price snapshot."""
import json
import sys
from pathlib import Path

# Resolve imports from the repository when this script is invoked by its path.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from research.costs import estimate_cost


def main():
    """Calculate labeled example costs without collecting AWS usage or billing data.

    Inputs:
        Retained price snapshot and explicitly stated example usage quantities.

    Outputs:
        None: Prints exact assumed-usage cost examples as JSON.
    """
    root = Path(__file__).resolve().parents[1]
    rates = json.loads((root / "protocol/baseline-price-snapshot.json").read_text())["rates"]
    examples = {
        "initial_24_hour_session_with_one_month_retention": {
            "config_items": 100, "config_rule_evaluations": 200, "securityhub_checks": 500,
            "s3_gb_months": 1, "s3_put_list_requests": 10000, "s3_get_requests": 10000,
            "cloudtrail_additional_management_events": 0,
        },
        "monthly_planning_example": {
            "config_items": 1000, "config_rule_evaluations": 2000, "securityhub_checks": 5000,
            "s3_gb_months": 1, "s3_put_list_requests": 10000, "s3_get_requests": 10000,
            "cloudtrail_additional_management_events": 0,
        },
    }
    print(json.dumps({name: {"assumptions": usage, **estimate_cost(usage, rates)} for name, usage in examples.items()}, indent=2))


if __name__ == "__main__":
    main()
