"""Source-locked protocol constants and proposed development observation names."""
PROPOSAL_SHA256 = "99ad4b0aa5e1af82346f5e8b0bb1e8388b48726dc8815b8f68bddf3df896f5db"
WINDOW_SECONDS = 1800
FACTS = {f"{time}.{name}" for time in ("start", "middle", "end") for name in (
    "tls_deny_present", "block_public_acls", "ignore_public_acls",
    "block_public_policy", "restrict_public_buckets", "versioning_enabled")}
