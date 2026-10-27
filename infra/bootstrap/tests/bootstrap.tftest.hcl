# State protection checks run with mocked AWS resources only.
# Supply synthetic provider responses for offline infrastructure tests.
# Inputs: declared fixture defaults. Outputs: mock values; no AWS session or deployment is used.
mock_provider "aws" {
  override_during = plan
  mock_data "aws_caller_identity" {
    defaults = { account_id = "653464153304", arn = "arn:aws:iam::653464153304:user/test-operator", user_id = "test" }
  }
  mock_resource "aws_s3_bucket" {
    defaults = { id = "dissertation-653464153304-us-east-2-state", arn = "arn:aws:s3:::dissertation-653464153304-us-east-2-state" }
  }
}
# Check protect state storage using the mocked configuration.
# Inputs: fixture values and proposed plan/apply behavior. Outputs: assertions that pass or fail the test run.
run "protect_state_storage" {
  command = plan
  assert {
    condition     = aws_s3_bucket_public_access_block.state.block_public_policy && aws_s3_bucket_public_access_block.state.restrict_public_buckets && one(aws_s3_bucket_versioning.state.versioning_configuration).status == "Enabled" && !aws_s3_bucket.state.force_destroy && jsondecode(aws_s3_bucket_policy.state.policy).Statement[0].Condition.Bool["aws:SecureTransport"] == "false"
    error_message = "State storage must stay private, versioned, TLS-only and protected from forced deletion."
  }
}

# Check retain customer key block using the mocked configuration.
# Inputs: fixture values and proposed plan/apply behavior. Outputs: assertions that pass or fail the test run.
run "retain_customer_key_block" {
  command = plan
  assert {
    condition     = contains(one(aws_s3_bucket_server_side_encryption_configuration.state.rule).blocked_encryption_types, "SSE-C")
    error_message = "State storage must retain the block on customer-provided encryption keys."
  }
}
