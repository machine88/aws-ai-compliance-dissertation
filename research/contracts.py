"""Source-locked protocol constants and proposed development observation names."""
# Input: the final proposal document fingerprint. Output: the source identity required by catalog validation.
PROPOSAL_SHA256 = "99ad4b0aa5e1af82346f5e8b0bb1e8388b48726dc8815b8f68bddf3df896f5db"
# Input: the proposal observation horizon. Output: the shared maximum trial duration, in seconds.
WINDOW_SECONDS = 1800
# Input: allowed observation times and technical property names. Output: the complete allowlist of fact keys.
FACTS = {f"{time}.{name}" for time in ("start", "middle", "end") for name in (
    "tls_deny_present", "block_public_acls", "ignore_public_acls",
    "block_public_policy", "restrict_public_buckets", "versioning_enabled")}
