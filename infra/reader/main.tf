# Input: explicit profile and isolated state key. Output: reader-access state only.
terraform {
  required_version = "~> 1.15.0"
  backend "s3" {
    bucket               = "dissertation-653464153304-us-east-2-state"
    key                  = "dissertation/653464153304/us-east-2/reader-access/terraform.tfstate"
    region               = "us-east-2"
    profile              = "dissertation"
    allowed_account_ids  = ["653464153304"]
    encrypt              = true
    use_lockfile         = true
    workspace_key_prefix = "dissertation/653464153304/us-east-2/reader-access/workspaces"
  }
  required_providers {
    aws = { source = "hashicorp/aws", version = "6.36.0" }
  }
}
# Input: existing provisioning profile. Output: account-guarded Ohio provider, no role widening.
provider "aws" {
  profile             = "dissertation"
  region              = "us-east-2"
  allowed_account_ids = ["653464153304"]
  default_tags { tags = { Project = "aws-ai-compliance-dissertation" } }
}
# Input: selected session. Output: current caller attributes used by the guard.
data "aws_caller_identity" "current" {}
# Input: live identity. Output: a guard refusing root, other users and alternate workspaces.
resource "terraform_data" "identity_guard" {
  lifecycle {
    precondition {
      condition     = data.aws_caller_identity.current.arn == "arn:aws:iam::653464153304:user/martin-morales-personal" && terraform.workspace == "default"
      error_message = "Use the reviewed non-root IAM user and default workspace."
    }
  }
}
# Inputs: read-only live inventory values, not invented IDs. Output: exact Config resource scope.
variable "config_rule_arns" {
  type = set(string)
  validation {
    condition     = length(var.config_rule_arns) == 2 && alltrue([for arn in var.config_rule_arns : can(regex("^arn:aws:config:us-east-2:653464153304:config-rule/config-rule-[a-z0-9]+$", arn))])
    error_message = "Supply the two verified deployed research Config rule ARNs."
  }
}
# Input: verified recorder ARN. Output: recorder-only permission scope.
variable "configuration_recorder_arn" {
  type = string
  validation {
    condition     = can(regex("^arn:aws:config:us-east-2:653464153304:configuration-recorder/dissertation-research/[a-z0-9-]+$", var.configuration_recorder_arn))
    error_message = "Supply the verified dissertation-research recorder ARN."
  }
}
# Inputs: generated action list and verified resources. Output: restrictive read-only ceiling.
locals {
  generated = jsondecode(file("${path.module}/generated-reader-policy.json"))
  actions   = distinct(flatten([for statement in local.generated.Statement : statement.Action]))
  region    = { StringEquals = { "aws:RequestedRegion" = "us-east-2" } }
  boundary = {
    Version = "2012-10-17"
    Statement = [
      { Sid = "BlockAllOtherActions", Effect = "Deny", NotAction = local.actions, Resource = "*" },
      { Sid = "Identity", Effect = "Allow", Action = ["sts:GetCallerIdentity"], Resource = "*" },
      { Sid = "BucketMetadata", Effect = "Allow", Action = [for action in local.actions : action if startswith(action, "s3:")], Resource = ["arn:aws:s3:::dissertation-research-653464153304-us-east-2-logs", "arn:aws:s3:::dissertation-653464153304-us-east-2-state"], Condition = local.region },
      { Sid = "Recorder", Effect = "Allow", Action = ["config:DescribeConfigurationRecorders", "config:DescribeConfigurationRecorderStatus"], Resource = [var.configuration_recorder_arn], Condition = local.region },
      { Sid = "Rules", Effect = "Allow", Action = ["config:GetComplianceDetailsByConfigRule"], Resource = var.config_rule_arns, Condition = local.region },
      { Sid = "DeliveryContext", Effect = "Allow", Action = ["config:DescribeDeliveryChannels"], Resource = "*", Condition = local.region },
      { Sid = "CSPM", Effect = "Allow", Action = ["securityhub:DescribeHub", "securityhub:GetEnabledStandards", "securityhub:GetFindings"], Resource = ["arn:aws:securityhub:us-east-2:653464153304:hub/default"], Condition = local.region },
      { Sid = "TrailStatus", Effect = "Allow", Action = ["cloudtrail:GetTrailStatus"], Resource = ["arn:aws:cloudtrail:us-east-2:653464153304:trail/dissertation-research"], Condition = local.region }
    ]
  }
}
# Input: reviewed boundary. Output: managed policy installed before role permissions.
resource "aws_iam_policy" "boundary" {
  name   = "dissertation-evidence-reader-boundary"
  policy = jsonencode(local.boundary)
}
# Input: unedited Autopilot identity-policy output. Output: generated baseline constrained by boundary.
resource "aws_iam_policy" "generated" {
  name   = "dissertation-evidence-reader-generated"
  policy = jsonencode(local.generated)
}
# Input: exact human principal and mandatory boundary. Output: one-hour temporary reader role.
resource "aws_iam_role" "reader" {
  name                 = "dissertation-evidence-reader"
  max_session_duration = 3600
  permissions_boundary = aws_iam_policy.boundary.arn
  assume_role_policy = jsonencode({
    Version   = "2012-10-17"
    Statement = [{ Effect = "Allow", Action = "sts:AssumeRole", Principal = { AWS = "arn:aws:iam::653464153304:user/martin-morales-personal" } }]
  })
  depends_on = [terraform_data.identity_guard]
}
# Input: role and generated baseline. Output: effective access intersected with its boundary.
resource "aws_iam_role_policy_attachment" "generated" {
  role       = aws_iam_role.reader.name
  policy_arn = aws_iam_policy.generated.arn
}
# Input: created role. Output: ARN for later reviewed local profile setup; no credentials.
output "reader_role_arn" { value = aws_iam_role.reader.arn }
