"""Pure checks for full-bucket empty listing receipts; never issues AWS requests."""
from research.sandbox_readiness import BUCKET

ACCOUNT = "653464153304"
REGION = "us-east-2"
LISTINGS = {
    "list_objects_v2": ("MaxKeys", "Name", ("Contents",),
                        ("ContinuationToken", "StartAfter", "NextContinuationToken")),
    "list_object_versions": ("MaxKeys", "Name", ("Versions", "DeleteMarkers"),
                             ("KeyMarker", "VersionIdMarker", "NextKeyMarker", "NextVersionIdMarker")),
    "list_multipart_uploads": ("MaxUploads", "Bucket", ("Uploads",),
                               ("KeyMarker", "UploadIdMarker", "NextKeyMarker", "NextUploadIdMarker")),
}


def verify_empty_sandbox_listings(receipts, bucket=BUCKET):
    """Reject incomplete, filtered or nonempty listing evidence for the fixed sandbox.

    Inputs:
        receipts: Exact three-operation map, each with region, request and response fields.
            Requests must cover the whole bucket from the beginning with expected owner and
            a 1000-entry page ceiling. Responses use parsed AWS SDK field names.
        bucket: Exact dedicated development sandbox name; all other names are rejected.
    Outputs:
        dict: Supplied-listing consistency result, with source/freshness/concurrency and
            scientific authorization gates false. No IO, AWS calls or input mutation occurs.
            ValueError rejects missing, malformed, filtered, partial or nonempty evidence.
    """
    if bucket != BUCKET or not isinstance(receipts, dict) or set(receipts) != set(LISTINGS):
        raise ValueError("Exact sandbox and three listing receipts required")
    for operation, (limit, name, collections, markers) in LISTINGS.items():
        receipt = receipts[operation]
        if not isinstance(receipt, dict) or set(receipt) != {"region", "request", "response"}:
            raise ValueError("Exact listing receipt envelope required")
        request, response = receipt["request"], receipt["response"]
        expected = {"Bucket": bucket, "ExpectedBucketOwner": ACCOUNT, limit: 1000}
        if receipt["region"] != REGION or not isinstance(request, dict) or request != expected or type(request.get(limit)) is not int:
            raise ValueError("Unfiltered first-page request with exact owner and region required")
        if not isinstance(response, dict) or "Error" in response or response.get(name) != bucket:
            raise ValueError("Successful response naming the exact bucket required")
        metadata = response.get("ResponseMetadata")
        if not isinstance(metadata, dict) or type(metadata.get("HTTPStatusCode")) is not int or metadata["HTTPStatusCode"] != 200:
            raise ValueError("Retained successful response metadata required")
        # An empty full bucket fits one page. Never follow pagination to reinterpret a failure.
        if response.get("IsTruncated") is not False:
            raise ValueError("Explicit complete listing required")
        for field in collections + ("CommonPrefixes",):
            if field in response and (not isinstance(response[field], list) or response[field] != []):
                raise ValueError("Listing must contain no objects, versions, markers, uploads or groups")
        for field in ("Prefix", "Delimiter") + markers:
            if field in response and response[field] != "":
                raise ValueError("Filtered or continuation listing cannot establish full emptiness")
        if limit in response and (type(response[limit]) is not int or response[limit] != 1000):
            raise ValueError("Response page ceiling differs from the request")
        if operation == "list_objects_v2" and (type(response.get("KeyCount")) is not int or response["KeyCount"] != 0):
            raise ValueError("Explicit zero current-object count required")
    # These independent calls are not an atomic snapshot or a durable exclusivity guarantee.
    return {"version": "sandbox-empty-listings-v0.1", "supplied_listings_empty": True,
            "source_identity_verified": False, "source_freshness_verified": False,
            "concurrent_writes_excluded": False, "mutation_authorized": False,
            "trigger_verified": False, "ml_ready": False, "research_trials": 0}


def verify_sandbox_prestate(metadata, receipts):
    """Combine preserved bucket protections and full-empty supplied listings without approval.

    Inputs:
        metadata: Exact nine-operation response map accepted by verify_sandbox_metadata.
        receipts: Three full-bucket listing receipts accepted by verify_empty_sandbox_listings.
    Outputs:
        dict: Both administrative consistency reports and live_execution_allowed=false.
            No IO or input mutation; raises ValueError if either predicate rejects evidence.
            Does not emit a recovery-planner event or authenticate either evidence source.
    """
    from research.sandbox_readiness import verify_sandbox_metadata

    # Keep each report intact: neither predicate supplies identity, clocks or exclusivity.
    protections = verify_sandbox_metadata(metadata)
    emptiness = verify_empty_sandbox_listings(receipts)
    return {"version": "sandbox-prestate-v0.1", "protections": protections,
            "empty_listings": emptiness, "live_execution_allowed": False}
