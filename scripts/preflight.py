"""Read-only target-account inventory. Uses an explicitly selected local profile."""
import argparse
import json
import subprocess

TARGET = "653464153304"

def aws(profile, region, *args):
    result = subprocess.run(["aws", "--profile", profile, "--region", region,
                             "--no-cli-pager", *args, "--output", "json"],
                            check=True, capture_output=True, text=True)
    return json.loads(result.stdout)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", required=True)
    parser.add_argument("--region", required=True)
    args = parser.parse_args()
    identity = aws(args.profile, args.region, "sts", "get-caller-identity")
    if identity.get("Account") != TARGET:
        raise SystemExit("Account mismatch; inventory refused")
    print(json.dumps({"identity": identity}))
    for service, operation in [("configservice", "describe-configuration-recorders"),
                               ("configservice", "describe-delivery-channels"),
                               ("securityhub", "describe-hub"),
                               ("securityhub", "get-enabled-standards"),
                               ("cloudtrail", "describe-trails")]:
        try:
            print(json.dumps({"service": service, "operation": operation,
                              "result": aws(args.profile, args.region, service, operation)}))
        except subprocess.CalledProcessError:
            print(json.dumps({"service": service, "operation": operation,
                              "status": "unverified: command failed; investigate before deployment"}))

if __name__ == "__main__":
    main()
