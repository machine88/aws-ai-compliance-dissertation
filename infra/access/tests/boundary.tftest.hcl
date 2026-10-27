# Check the trust and boundary relationship without contacting AWS.
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
