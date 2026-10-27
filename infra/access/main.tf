# This root prepares access only; applying it requires separate approval.
terraform {
  required_version = "~> 1.14.0"
  backend "local" { path = "access.tfstate" }
  required_providers {
    aws = { source = "hashicorp/aws", version = "6.36.0" }
  }
}
provider "aws" {
  profile             = "dissertation"
  region              = "us-east-2"
  allowed_account_ids = ["653464153304"]
  default_tags { tags = { Project = "aws-ai-compliance-dissertation" } }
}
data "aws_caller_identity" "current" {}
resource "terraform_data" "identity_guard" {
  lifecycle {
    precondition {
      condition     = !endswith(data.aws_caller_identity.current.arn, ":root")
      error_message = "Use a non-root identity in the approved account."
    }
  }
}
# Install the boundary when the role is created, before granting any policies.
resource "aws_iam_policy" "boundary" {
  name   = "dissertation-paused-baseline-boundary"
  policy = file("${path.module}/deployment-boundary.json")
}
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
resource "aws_iam_policy" "generated" {
  name   = "dissertation-baseline-generated"
  policy = file("${path.module}/generated-baseline-policy.json")
}
resource "aws_iam_policy" "backend_reads" {
  name   = "dissertation-baseline-state-and-reads"
  policy = file("${path.module}/backend-and-read-policy.json")
}
resource "aws_iam_role_policy_attachment" "generated" {
  role       = aws_iam_role.deployment.name
  policy_arn = aws_iam_policy.generated.arn
}
resource "aws_iam_role_policy_attachment" "backend_reads" {
  role       = aws_iam_role.deployment.name
  policy_arn = aws_iam_policy.backend_reads.arn
}
output "deployment_role_arn" { value = aws_iam_role.deployment.arn }
