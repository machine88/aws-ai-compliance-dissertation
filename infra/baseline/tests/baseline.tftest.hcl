# All plans use a mock provider: no credentials, service changes or AWS charges.
mock_provider "aws" {
  override_during = plan
  mock_data "aws_caller_identity" {
    defaults = {
      account_id = "653464153304"
      arn        = "arn:aws:sts::653464153304:assumed-role/dissertation-paused-baseline-deploy/offline-test"
      user_id    = "test-operator"
    }
  }
  mock_resource "aws_s3_bucket" {
    defaults = {
      id  = "dissertation-research-653464153304-us-east-2-logs"
      arn = "arn:aws:s3:::dissertation-research-653464153304-us-east-2-logs"
    }
  }
  mock_resource "aws_iam_service_linked_role" {
    defaults = { arn = "arn:aws:iam::653464153304:role/aws-service-role/config.amazonaws.com/AWSServiceRoleForConfig" }
  }
  mock_resource "aws_securityhub_standards_subscription" {
    defaults = { id = "arn:aws:securityhub:us-east-2:653464153304:subscription/aws-foundational-security-best-practices/v/1.0.0" }
  }
}

mock_provider "aws" {
  alias = "billing"
}

variables {
  budget_email = "offline-test@example.invalid"
}

# Paused collection remains the default and every evidence bucket setting stays protective.
run "paused_and_private_by_default" {
  command = plan
  assert {
    condition     = !aws_config_configuration_recorder_status.research.is_enabled && !aws_cloudtrail.research.enable_logging && length(aws_securityhub_standards_subscription.fsbp) == 0
    error_message = "Collection must not start by default."
  }
  assert {
    condition     = aws_s3_bucket_public_access_block.telemetry.block_public_acls && aws_s3_bucket_public_access_block.telemetry.block_public_policy && aws_s3_bucket_public_access_block.telemetry.ignore_public_acls && aws_s3_bucket_public_access_block.telemetry.restrict_public_buckets && !aws_s3_bucket.telemetry.force_destroy
    error_message = "Evidence storage must block public access and refuse forced deletion."
  }
  assert {
    condition     = one(aws_s3_bucket_versioning.telemetry.versioning_configuration).status == "Enabled" && one(one(aws_s3_bucket_server_side_encryption_configuration.telemetry.rule).apply_server_side_encryption_by_default).sse_algorithm == "AES256"
    error_message = "Retain encrypted, versioned evidence."
  }
}

# Baseline control coverage is explicitly scoped; unrelated standard controls stay disabled.
run "collection_scope_and_delivery_policies" {
  command = plan
  variables {
    enable_collection = true
  }
  assert {
    condition     = length([for control in aws_securityhub_standards_control.fsbp : control if control.control_status == "ENABLED"]) == 2 && aws_securityhub_standards_control.fsbp["S3.5"].control_status == "ENABLED" && aws_securityhub_standards_control.fsbp["S3.8"].control_status == "ENABLED" && aws_securityhub_standards_control.fsbp["EC2.1"].control_status == "DISABLED"
    error_message = "Only the two S3 instrument candidates should be enabled."
  }
  assert {
    condition     = aws_securityhub_standards_control.fsbp["S3.5"].standards_control_arn == "arn:aws:securityhub:us-east-2:653464153304:control/aws-foundational-security-best-practices/v/1.0.0/S3.5" && !aws_securityhub_account.research.enable_default_standards && !aws_securityhub_account.research.auto_enable_controls
    error_message = "Control ARNs and baseline freezing must be correct."
  }
  assert {
    condition     = !one(aws_config_configuration_recorder.research.recording_group).all_supported && toset(one(aws_config_configuration_recorder.research.recording_group).resource_types) == toset(["AWS::S3::Bucket"]) && alltrue([for rule in aws_config_config_rule.s3 : one(rule.scope).tag_value == "aws-ai-compliance-dissertation" && one(rule.scope).tag_key == "Project" && length(coalesce(one(rule.scope).compliance_resource_types, [])) == 0])
    error_message = "Record only S3 types; use tag-only scope for managed S3 rules, without incompatible resource-type scope."
  }
  assert {
    condition     = aws_cloudtrail.research.enable_log_file_validation && !aws_cloudtrail.research.is_multi_region_trail && length(one(aws_cloudtrail.research.event_selector).data_resource) == 0
    error_message = "Keep a validated, single-region management trail without data events."
  }
  assert {
    condition     = alltrue([for s in jsondecode(aws_s3_bucket_policy.telemetry.policy).Statement : contains(keys(s.Condition), "StringEquals") ? (s.Sid == "CloudTrailDelivery" ? s.Condition.StringEquals["aws:SourceArn"] == "arn:aws:cloudtrail:us-east-2:653464153304:trail/dissertation-research" : true) : true]) && jsondecode(aws_s3_bucket_policy.telemetry.policy).Statement[0].Effect == "Deny"
    error_message = "Delivery policy must retain its trail restriction and TLS denial."
  }
}

# Account and input failures must stop planning rather than silently broadening scope.
run "reject_root" {
  command = plan
  override_data {
    target = data.aws_caller_identity.current
    values = { account_id = "653464153304", arn = "arn:aws:iam::653464153304:root" }
  }
  expect_failures = [terraform_data.identity_guard]
}
run "reject_wrong_account" {
  command = plan
  override_data {
    target = data.aws_caller_identity.current
    values = { account_id = "000000000000", arn = "arn:aws:iam::000000000000:user/test" }
  }
  expect_failures = [terraform_data.identity_guard]
}
run "reject_other_region" {
  command = plan
  variables { region = "us-west-2" }
  expect_failures = [var.region]
}
run "reject_unreviewed_control" {
  command = plan
  variables { enabled_security_controls = ["EC2.1"] }
  expect_failures = [var.enabled_security_controls]
}

# Even a valid account user must not bypass the bounded deployment role.
run "reject_unbounded_user" {
  command = plan
  override_data {
    target = data.aws_caller_identity.current
    values = { account_id = "653464153304", arn = "arn:aws:iam::653464153304:user/test-operator" }
  }
  expect_failures = [terraform_data.identity_guard]
}
