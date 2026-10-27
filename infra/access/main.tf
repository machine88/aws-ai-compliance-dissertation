# This root prepares access only; applying it requires separate approval.
# Select compatible tools, provider versions and isolated state storage.
# Inputs: version constraints and non-secret backend settings. Outputs: the initialization/state configuration.
terraform {
  required_version = "~> 1.15.0"
  backend "s3" {
    bucket               = "dissertation-653464153304-us-east-2-state"
    key                  = "dissertation/653464153304/us-east-2/access/terraform.tfstate"
    region               = "us-east-2"
    profile              = "dissertation"
    allowed_account_ids  = ["653464153304"]
    encrypt              = true
    use_lockfile         = true
    workspace_key_prefix = "dissertation/653464153304/us-east-2/access/workspaces"
  }
  required_providers {
    aws = { source = "hashicorp/aws", version = "6.36.0" }
  }
}
# Configure the explicit provisioning session in the reviewed account and region.
# Inputs: local profile, region and any declared role settings. Outputs: the authenticated client used by this provider alias.
provider "aws" {
  profile             = "dissertation"
  region              = "us-east-2"
  allowed_account_ids = ["653464153304"]
  default_tags { tags = { Project = "aws-ai-compliance-dissertation" } }
}
# Read the selected AWS caller identity without creating resources.
# Inputs: the configured provider session. Outputs: account ID, caller ARN and user identifier.
data "aws_caller_identity" "current" {}
# Stop unsafe identities before resource provisioning begins.
# Inputs: the referenced variables, policy or resource IDs. Outputs: this resource's managed state and exported attributes.
resource "terraform_data" "identity_guard" {
  lifecycle {
    precondition {
      condition     = !endswith(data.aws_caller_identity.current.arn, ":root")
      error_message = "Use a non-root identity in the approved account."
    }
  }
}
# Install the boundary when the role is created, before granting any policies.
# Install the reviewed IAM policy document.
# Inputs: the referenced variables, policy or resource IDs. Outputs: this resource's managed state and exported attributes.
resource "aws_iam_policy" "boundary" {
  name   = "dissertation-paused-baseline-boundary"
  policy = file("${path.module}/deployment-boundary.json")
}
# Create the bounded deployment role with its restricted trust policy.
# Inputs: the referenced variables, policy or resource IDs. Outputs: this resource's managed state and exported attributes.
resource "aws_iam_role" "deployment" {
  name                 = "dissertation-paused-baseline-deploy"
  max_session_duration = 3600
  permissions_boundary = aws_iam_policy.boundary.arn
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Action    = "sts:AssumeRole"
      Principal = { AWS = "arn:aws:iam::653464153304:user/martin-morales-personal" }
    }]
  })
  depends_on = [terraform_data.identity_guard]
}
# Autopilot output is preserved; the mandatory boundary limits its broad grants.
# Install the reviewed IAM policy document.
# Inputs: the referenced variables, policy or resource IDs. Outputs: this resource's managed state and exported attributes.
resource "aws_iam_policy" "generated" {
  name   = "dissertation-baseline-generated"
  policy = file("${path.module}/generated-baseline-policy.json")
}
# Install the reviewed IAM policy document.
# Inputs: the referenced variables, policy or resource IDs. Outputs: this resource's managed state and exported attributes.
resource "aws_iam_policy" "backend_reads" {
  name   = "dissertation-baseline-state-and-reads"
  policy = file("${path.module}/backend-and-read-policy.json")
}
# Attach a policy to the explicitly named deployment role.
# Inputs: the referenced variables, policy or resource IDs. Outputs: this resource's managed state and exported attributes.
resource "aws_iam_role_policy_attachment" "generated" {
  role       = aws_iam_role.deployment.name
  policy_arn = aws_iam_policy.generated.arn
}
# Attach a policy to the explicitly named deployment role.
# Inputs: the referenced variables, policy or resource IDs. Outputs: this resource's managed state and exported attributes.
resource "aws_iam_role_policy_attachment" "backend_reads" {
  role       = aws_iam_role.deployment.name
  policy_arn = aws_iam_policy.backend_reads.arn
}
# Expose deployment_role_arn for verification and downstream tooling.
# Inputs: the referenced resource attribute or protocol value. Outputs: this named Terraform result.
output "deployment_role_arn" { value = aws_iam_role.deployment.arn }
