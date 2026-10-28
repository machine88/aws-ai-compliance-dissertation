# Check the trust and boundary relationship without contacting AWS.
# Supply synthetic provider responses for offline infrastructure tests.
# Inputs: declared fixture defaults. Outputs: mock values; no AWS session or deployment is used.
mock_provider "aws" {
  mock_resource "aws_iam_policy" {
    defaults = { arn = "arn:aws:iam::653464153304:policy/mock-policy" }
  }
  mock_data "aws_caller_identity" {
    defaults = {
      account_id = "653464153304"
      arn        = "arn:aws:iam::653464153304:user/martin-morales-personal"
    }
  }
}
# Check restricted role using the mocked configuration.
# Inputs: fixture values and proposed plan/apply behavior. Outputs: assertions that pass or fail the test run.
run "restricted_role" {
  command = apply
  assert {
    condition     = aws_iam_role.deployment.permissions_boundary == aws_iam_policy.boundary.arn
    error_message = "The deployment role must be created with its boundary."
  }
  assert {
    condition     = aws_iam_role.deployment.max_session_duration == 3600
    error_message = "Deployment sessions must be limited to one hour."
  }
  assert {
    condition     = jsondecode(aws_iam_role.deployment.assume_role_policy).Statement[0].Principal.AWS == "arn:aws:iam::653464153304:user/martin-morales-personal"
    error_message = "Only the reviewed IAM user may assume this role."
  }
}

# Input: proposed trail-only start permission. Output: exact existing trail/region scope and no Config start.
run "trail_start_remains_named_and_regional" {
  command = plan
  assert {
    condition     = contains(one([for statement in jsondecode(aws_iam_policy.boundary.policy).Statement : statement if statement.Sid == "B12"]).Action, "cloudtrail:StartLogging") && one([for statement in jsondecode(aws_iam_policy.boundary.policy).Statement : statement if statement.Sid == "B12"]).Resource == ["arn:aws:cloudtrail:us-east-2:653464153304:trail/dissertation-research"] && one([for statement in jsondecode(aws_iam_policy.boundary.policy).Statement : statement if statement.Sid == "B12"]).Condition.StringEquals["aws:RequestedRegion"] == "us-east-2"
    error_message = "StartLogging must remain limited to the existing research trail in Ohio."
  }
  assert {
    condition     = !strcontains(aws_iam_policy.boundary.policy, "config:StartConfigurationRecorder") && aws_iam_role.deployment.max_session_duration == 3600 && aws_iam_role.deployment.permissions_boundary == aws_iam_policy.boundary.arn
    error_message = "The trail stage must not add Config start, remove the boundary or extend sessions."
  }
}
