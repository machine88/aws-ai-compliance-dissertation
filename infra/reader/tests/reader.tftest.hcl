# Inputs: synthetic ARNs only. Outputs: provider-free access-boundary checks.
mock_provider "aws" {
  mock_resource "aws_iam_policy" { defaults = { arn = "arn:aws:iam::653464153304:policy/synthetic" } }
  mock_data "aws_caller_identity" {
    defaults = { account_id = "653464153304", arn = "arn:aws:iam::653464153304:user/martin-morales-personal" }
  }
}
# Inputs: fake deployed identifiers. Outputs: test values, never live inventory.
variables {
  config_rule_arns           = ["arn:aws:config:us-east-2:653464153304:config-rule/config-rule-test1", "arn:aws:config:us-east-2:653464153304:config-rule/config-rule-test2"]
  configuration_recorder_arn = "arn:aws:config:us-east-2:653464153304:configuration-recorder/dissertation-research/synthetic"
}
# Inputs: mocked apply. Outputs: boundary, trust, action and resource regression assertions.
run "bounded_reader" {
  command = apply
  assert {
    condition     = aws_iam_role.reader.permissions_boundary == aws_iam_policy.boundary.arn && aws_iam_role.reader.max_session_duration == 3600
    error_message = "Reader requires a boundary and one-hour sessions."
  }
  assert {
    condition     = jsondecode(aws_iam_role.reader.assume_role_policy).Statement[0].Principal.AWS == "arn:aws:iam::653464153304:user/martin-morales-personal"
    error_message = "Trust must remain limited to the reviewed user."
  }
  assert {
    condition     = alltrue([for action in local.actions : (can(regex("^[^:]+:(Get|Describe)", action)) || action == "cloudtrail:LookupEvents")]) && !contains(local.actions, "s3:GetObject") && !contains(local.actions, "sts:AssumeRole")
    error_message = "Reader must have no mutation, object-content or role-chaining action."
  }
  assert {
    condition     = contains(local.actions, "cloudtrail:LookupEvents") && local.boundary.Statement[7].Action == ["cloudtrail:LookupEvents"] && local.boundary.Statement[7].Resource == "*" && local.boundary.Statement[7].Condition.StringEquals["aws:RequestedRegion"] == "us-east-2"
    error_message = "History inspection must use exactly LookupEvents with its Ohio condition."
  }
  assert {
    condition     = local.boundary.Statement[0].Effect == "Deny" && local.boundary.Statement[0].NotAction == local.actions && length(local.boundary.Statement[2].Resource) == 2 && local.boundary.Statement[4].Resource == var.config_rule_arns
    error_message = "Explicit action ceiling and exact resource scopes must be retained."
  }
}
# Input: forbidden root fixture. Output: rejected provisioning identity.
run "reject_root" {
  command = plan
  override_data {
    target = data.aws_caller_identity.current
    values = { account_id = "653464153304", arn = "arn:aws:iam::653464153304:root" }
  }
  expect_failures = [terraform_data.identity_guard]
}
