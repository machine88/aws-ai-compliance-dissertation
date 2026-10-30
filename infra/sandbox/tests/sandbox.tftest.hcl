# Inputs: synthetic identity/bucket attributes. Outputs: offline plans with no AWS calls.
mock_provider "aws" {
  override_during = plan
  mock_data "aws_caller_identity" {
    defaults = {
      account_id = "653464153304"
      arn        = "arn:aws:sts::653464153304:assumed-role/dissertation-sandbox-deploy/offline-test"
      user_id    = "synthetic"
    }
  }
  mock_resource "aws_s3_bucket" {
    defaults = {
      id  = "dissertation-sandbox-653464153304-us-east-2-s3-01"
      arn = "arn:aws:s3:::dissertation-sandbox-653464153304-us-east-2-s3-01"
    }
  }
}

# Input: unchanged defaults. Output: no managed sandbox resources or target output.
run "disabled_by_default" {
  command = plan
  assert {
    condition     = length(aws_s3_bucket.sandbox) == 0 && length(terraform_data.scope_guard) == 0 && length(aws_s3_bucket_policy.sandbox) == 0 && output.sandbox_bucket_name == null
    error_message = "Default planning must not request sandbox creation."
  }
}

# Inputs: explicit creation and synthetic review hash. Outputs: fixed target and protected storage.
run "reviewed_secure_scaffold" {
  command = plan
  variables {
    create_sandbox           = true
    deployment_review_sha256 = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
  }
  assert {
    condition     = output.sandbox_bucket_name == "dissertation-sandbox-653464153304-us-east-2-s3-01" && !aws_s3_bucket.sandbox[0].force_destroy
    error_message = "Only the reserved sandbox may be requested, without forced deletion."
  }
  assert {
    condition     = aws_s3_bucket_public_access_block.sandbox[0].block_public_acls && aws_s3_bucket_public_access_block.sandbox[0].block_public_policy && aws_s3_bucket_public_access_block.sandbox[0].ignore_public_acls && aws_s3_bucket_public_access_block.sandbox[0].restrict_public_buckets && one(aws_s3_bucket_ownership_controls.sandbox[0].rule).object_ownership == "BucketOwnerEnforced"
    error_message = "Public access must stay blocked and ACLs disabled."
  }
  assert {
    condition     = one(aws_s3_bucket_versioning.sandbox[0].versioning_configuration).status == "Enabled" && one(one(aws_s3_bucket_server_side_encryption_configuration.sandbox[0].rule).apply_server_side_encryption_by_default).sse_algorithm == "AES256" && contains(one(aws_s3_bucket_server_side_encryption_configuration.sandbox[0].rule).blocked_encryption_types, "SSE-C")
    error_message = "Versioning and encryption protections must be explicit."
  }
  assert {
    condition     = length(jsondecode(aws_s3_bucket_policy.sandbox[0].policy).Statement) == 1 && jsondecode(aws_s3_bucket_policy.sandbox[0].policy).Statement[0].Effect == "Deny" && jsondecode(aws_s3_bucket_policy.sandbox[0].policy).Statement[0].Condition.Bool["aws:SecureTransport"] == "false" && toset(jsondecode(aws_s3_bucket_policy.sandbox[0].policy).Statement[0].Resource) == toset(["arn:aws:s3:::dissertation-sandbox-653464153304-us-east-2-s3-01", "arn:aws:s3:::dissertation-sandbox-653464153304-us-east-2-s3-01/*"])
    error_message = "TLS policy must deny insecure transport only on the sandbox and grant no access."
  }
}

# Input: creation without a review reference. Output: fail before any bucket provisioning.
run "reject_missing_review" {
  command = plan
  variables { create_sandbox = true }
  expect_failures = [terraform_data.scope_guard]
}

# Input: malformed provenance reference. Output: variable validation failure.
run "reject_bad_review" {
  command = plan
  variables { deployment_review_sha256 = "not-a-review-hash" }
  expect_failures = [var.deployment_review_sha256]
}

# Input: root identity. Output: reject even in the correct account.
run "reject_root" {
  command = plan
  variables {
    create_sandbox           = true
    deployment_review_sha256 = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
  }
  override_data {
    target = data.aws_caller_identity.current
    values = { account_id = "653464153304", arn = "arn:aws:iam::653464153304:root" }
  }
  expect_failures = [terraform_data.scope_guard]
}

# Input: human provisioning identity. Output: no fallback from the bounded role.
run "reject_unbounded_user" {
  command = plan
  variables {
    create_sandbox           = true
    deployment_review_sha256 = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
  }
  override_data {
    target = data.aws_caller_identity.current
    values = { account_id = "653464153304", arn = "arn:aws:iam::653464153304:user/martin-morales-personal" }
  }
  expect_failures = [terraform_data.scope_guard]
}

# Input: role in a different account. Output: reject cross-account provisioning.
run "reject_wrong_account" {
  command = plan
  variables {
    create_sandbox           = true
    deployment_review_sha256 = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
  }
  override_data {
    target = data.aws_caller_identity.current
    values = { account_id = "000000000000", arn = "arn:aws:sts::000000000000:assumed-role/dissertation-sandbox-deploy/test" }
  }
  expect_failures = [terraform_data.scope_guard]
}
