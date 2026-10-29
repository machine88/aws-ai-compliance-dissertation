"""Silent native worker for a reviewed read-only snapshot; never execute without capture approval."""
import json
import os
import stat
import sys
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from research.archive_ingestion import unique_object, reject_constant
from research.aws_reader import ACCOUNT, REGION
from research.native_capture import READER_ROLE, validate_native_scope, worker_environment
from research.prospective_runner import CollectorAbort
from research.trials import safe_id
from scripts.collect_snapshot import main as snapshot_main

PROFILE = "_dissertation_prospective_reader"


def reader_session(session_factory=None, core_factory=None):
    """Verify the non-root source and construct the dedicated role profile only in memory.

    Inputs:
        session_factory: Optional injectable boto3 Session factory; None uses the installed SDK.
        core_factory: Optional injectable botocore session factory; None uses the installed SDK.
    Outputs:
        Session: Auto-refreshing evidence-reader SDK session, never exported or written to a profile.
            Issues only source STS identity here; role resolution occurs when the collector uses it.
            Wrong identity or unsupported source authentication raises ValueError before resource reads.
    """
    import boto3
    import botocore.session
    from botocore.config import Config
    factory = boto3.Session if session_factory is None else session_factory
    make_core = botocore.session.get_session if core_factory is None else core_factory
    if not callable(factory) or not callable(make_core):
        raise ValueError("Explicit SDK session factories must be callable")
    config = Config(connect_timeout=5, read_timeout=15, retries={"total_max_attempts": 3, "mode": "standard"},
                    ignore_configured_endpoint_urls=True)
    source_core = make_core()
    source_core.set_config_variable("profile", "dissertation")
    source_core.set_config_variable("region", REGION)
    source_core.set_default_client_config(config)
    source_config = source_core.get_scoped_config()
    forbidden = {"credential_process", "aws_access_key_id", "aws_secret_access_key", "aws_session_token",
                 "role_arn", "web_identity_token_file", "sso_session", "sso_start_url"}
    if not source_config.get("login_session") or forbidden & set(source_config):
        raise ValueError("Use the existing local-login dissertation source profile")
    source = factory(botocore_session=source_core, region_name=REGION)
    identity = source.client("sts", region_name=REGION, config=config).get_caller_identity()
    if identity.get("Account") != ACCOUNT or identity.get("Arn") != f"arn:aws:iam::{ACCOUNT}:user/martin-morales-personal":
        raise ValueError("Expected non-root provisioning identity required")
    # A separate core avoids accidentally reusing the already-resolved source credentials.
    core = make_core()
    core.full_config["profiles"][PROFILE] = {"role_arn": READER_ROLE, "source_profile": "dissertation",
                                            "role_session_name": "dissertation-prospective-reader",
                                            "duration_seconds": 900, "region": REGION}
    core.set_config_variable("profile", PROFILE)
    core.set_config_variable("region", REGION)
    core.set_default_client_config(config)
    return factory(botocore_session=core, region_name=REGION)


def main(arguments=None, input_stream=None):
    """Validate a bounded stdin descriptor and run the existing encrypted collector silently.

    Inputs:
        arguments: Optional argument list; only an empty list is accepted for this internal worker.
        input_stream: Optional binary stdin substitute for offline tests; None uses process stdin.
    Outputs:
        int: Zero for collector success, one for capture failure, two for fatal descriptor/source failure.
            Never prints evidence/errors; source credentials remain inside the SDK process.
    """
    try:
        arguments = sys.argv[1:] if arguments is None else arguments
        if arguments:
            return 2
        stream = sys.stdin.buffer if input_stream is None else input_stream
        encoded = stream.read(65537)
        if len(encoded) > 65536:
            return 2
        descriptor = json.loads(encoded, object_pairs_hook=unique_object, parse_constant=reject_constant)
        if set(descriptor) != {"scope", "approved_scope_sha256", "certificate", "sample_id"}:
            return 2
        scope, certificate = descriptor["scope"], Path(descriptor["certificate"])
        validate_native_scope(scope, descriptor["approved_scope_sha256"], certificate)
        root = Path(scope["output_root"])
        if certificate != root / "journal" / "recipient-public.pem" or certificate.is_symlink():
            return 2
        for directory in (root, root / "samples", root / "journal"):
            info = directory.lstat()
            if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
                return 2
        if os.environ.get("AWS_EC2_METADATA_DISABLED") != "true" or os.environ.get("AWS_IGNORE_CONFIGURED_ENDPOINT_URLS") != "true":
            return 2
        allowed = {"AWS_EC2_METADATA_DISABLED", "AWS_REGION", "AWS_DEFAULT_REGION", "AWS_IGNORE_CONFIGURED_ENDPOINT_URLS", "AWS_MAX_ATTEMPTS", "AWS_RETRY_MODE"}
        if any(key.startswith("AWS_") and key not in allowed for key in os.environ):
            return 2
        expected_environment = worker_environment()
        if any(os.environ.get(key) != expected_environment[key] for key in allowed):
            return 2
        sample_id = safe_id(descriptor["sample_id"])
        output = root / "samples" / sample_id
    except Exception:
        return 2

    def factory(profile_name, region_name):
        """Resolve the role lazily, after the existing collector validates local encryption.

        Inputs:
            profile_name: Exact internal profile passed to the existing snapshot CLI.
            region_name: Required Ohio SDK region.
        Outputs:
            Session: Dedicated in-memory reader session; source failures abort without resource reads.
        """
        try:
            if profile_name != PROFILE or region_name != REGION:
                raise ValueError("Unexpected worker session scope")
            return reader_session()
        except Exception:
            raise CollectorAbort("Source identity/session validation failed") from None
    try:
        with open(os.devnull, "w") as sink, redirect_stdout(sink), redirect_stderr(sink):
            return snapshot_main(["--bucket", scope["bucket"], "--profile", PROFILE, "--output", str(output),
                                  "--recipient-cert", str(certificate), "--openssl", scope["openssl_executable"],
                                  "--max-items", str(scope["max_items"]), "--max-pages", str(scope["max_pages"])],
                                 session_factory=factory)
    except CollectorAbort:
        return 2
    except Exception:
        return 1


if __name__ == "__main__":
    sys.exit(main())
