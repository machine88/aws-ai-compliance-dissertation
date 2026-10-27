# Bootstrap state is isolated in the approved protected S3 bucket.
# Select compatible tools, provider versions and isolated state storage.
# Inputs: version constraints and non-secret backend settings. Outputs: the initialization/state configuration.
terraform {
  required_version = "~> 1.15.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "= 6.36.0"
    }
  }
  backend "s3" {
    bucket               = "dissertation-653464153304-us-east-2-state"
    key                  = "dissertation/653464153304/us-east-2/bootstrap/terraform.tfstate"
    region               = "us-east-2"
    profile              = "dissertation"
    allowed_account_ids  = ["653464153304"]
    encrypt              = true
    use_lockfile         = true
    workspace_key_prefix = "dissertation/653464153304/us-east-2/bootstrap/workspaces"
  }
}

# Configure the explicit provisioning session in the reviewed account and region.
# Inputs: local profile, region and any declared role settings. Outputs: the authenticated client used by this provider alias.
provider "aws" {
  region              = "us-east-2"
  profile             = "dissertation"
  allowed_account_ids = ["653464153304"]
  default_tags {
    tags = { Project = "aws-ai-compliance-dissertation", ManagedBy = "Terraform", Phase = "bootstrap" }
  }
}

# Read the selected AWS caller identity without creating resources.
# Inputs: the configured provider session. Outputs: account ID, caller ARN and user identifier.
data "aws_caller_identity" "current" {}

# Root cannot provision state storage even in the correct account.
# Stop unsafe identities before resource provisioning begins.
# Inputs: the referenced variables, policy or resource IDs. Outputs: this resource's managed state and exported attributes.
resource "terraform_data" "identity_guard" {
  input = data.aws_caller_identity.current.account_id
  lifecycle {
    precondition {
      condition     = data.aws_caller_identity.current.account_id == "653464153304" && !endswith(data.aws_caller_identity.current.arn, ":root")
      error_message = "Use a non-root identity in account 653464153304."
    }
  }
}

# Create a separately named protected S3 bucket.
# Inputs: the referenced variables, policy or resource IDs. Outputs: this resource's managed state and exported attributes.
resource "aws_s3_bucket" "state" {
  bucket        = "dissertation-653464153304-us-east-2-state"
  force_destroy = false
  lifecycle {
    prevent_destroy = true
  }
  depends_on = [terraform_data.identity_guard]
}

# Block public bucket and object access.
# Inputs: the referenced variables, policy or resource IDs. Outputs: this resource's managed state and exported attributes.
resource "aws_s3_bucket_public_access_block" "state" {
  bucket                  = aws_s3_bucket.state.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Keep bucket ownership enforced and ACL-based ownership disabled.
# Inputs: the referenced variables, policy or resource IDs. Outputs: this resource's managed state and exported attributes.
resource "aws_s3_bucket_ownership_controls" "state" {
  bucket = aws_s3_bucket.state.id
  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

# Retain previous object versions for recovery.
# Inputs: the referenced variables, policy or resource IDs. Outputs: this resource's managed state and exported attributes.
resource "aws_s3_bucket_versioning" "state" {
  bucket = aws_s3_bucket.state.id
  versioning_configuration {
    status = "Enabled"
  }
}

# Configure encryption at rest and retain the SSE-C block.
# Inputs: the referenced variables, policy or resource IDs. Outputs: this resource's managed state and exported attributes.
resource "aws_s3_bucket_server_side_encryption_configuration" "state" {
  bucket = aws_s3_bucket.state.id
  rule {
    # Preserve the block on customer-provided encryption keys for state and logs.
    blocked_encryption_types = ["SSE-C"]
    bucket_key_enabled       = false
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# Lock objects live beside each state key; TLS is required for both kinds of objects.
# Restrict bucket access and enforce the reviewed delivery/TLS conditions.
# Inputs: the referenced variables, policy or resource IDs. Outputs: this resource's managed state and exported attributes.
resource "aws_s3_bucket_policy" "state" {
  bucket = aws_s3_bucket.state.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "RequireTLS", Effect = "Deny", Principal = "*", Action = "s3:*"
      Resource  = [aws_s3_bucket.state.arn, "${aws_s3_bucket.state.arn}/*"]
      Condition = { Bool = { "aws:SecureTransport" = "false" } }
    }]
  })
  depends_on = [aws_s3_bucket_public_access_block.state]
}

# Expose state_bucket for verification and downstream tooling.
# Inputs: the referenced resource attribute or protocol value. Outputs: this named Terraform result.
output "state_bucket" {
  value = aws_s3_bucket.state.id
}
