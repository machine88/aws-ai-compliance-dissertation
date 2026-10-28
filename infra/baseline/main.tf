# Regional monitoring baseline. Applying this configuration requires separate user approval.
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
    key                  = "dissertation/653464153304/us-east-2/baseline/terraform.tfstate"
    region               = "us-east-2"
    profile              = "dissertation"
    allowed_account_ids  = ["653464153304"]
    encrypt              = true
    use_lockfile         = true
    workspace_key_prefix = "dissertation/653464153304/us-east-2/baseline/workspaces"
    assume_role = {
      role_arn     = "arn:aws:iam::653464153304:role/dissertation-paused-baseline-deploy"
      session_name = "dissertation-baseline-state"
    }
  }
}

# Never resolve credentials from an implicit default profile or another AWS account.
# Configure the explicit account, region and bounded deployment session.
# Inputs: local profile, region and any declared role settings. Outputs: the authenticated client used by this provider alias.
provider "aws" {
  region              = var.region
  profile             = var.aws_profile
  allowed_account_ids = ["653464153304"]
  # Both regional and billing operations must use the bounded deployment role.
  assume_role {
    role_arn     = "arn:aws:iam::653464153304:role/dissertation-paused-baseline-deploy"
    session_name = "dissertation-baseline-deploy"
  }
  default_tags {
    tags = {
      Project   = "aws-ai-compliance-dissertation"
      ManagedBy = "Terraform"
      Phase     = "baseline"
    }
  }
}

# Billing is global and uses the Northern Virginia API endpoint.
# Configure the explicit account, region and bounded deployment session.
# Inputs: local profile, region and any declared role settings. Outputs: the authenticated client used by this provider alias.
provider "aws" {
  alias               = "billing"
  region              = "us-east-1"
  profile             = var.aws_profile
  allowed_account_ids = ["653464153304"]
  # Both regional and billing operations must use the bounded deployment role.
  assume_role {
    role_arn     = "arn:aws:iam::653464153304:role/dissertation-paused-baseline-deploy"
    session_name = "dissertation-baseline-deploy"
  }
}

# Read the selected AWS caller identity without creating resources.
# Inputs: the configured provider session. Outputs: account ID, caller ARN and user identifier.
data "aws_caller_identity" "current" {}

# Derive consistent account, resource and control identifiers.
# Inputs: fixed study scope and reviewed configuration. Outputs: named values reused by the resources below.
locals {
  account_id = "653464153304"
  prefix     = "dissertation-research"
  log_bucket = "${local.prefix}-${local.account_id}-${var.region}-logs"
  trail_arn  = "arn:aws:cloudtrail:${var.region}:${local.account_id}:trail/${local.prefix}"
  fsbp_arn   = "arn:aws:securityhub:${var.region}::standards/aws-foundational-security-best-practices/v/1.0.0"
  fsbp       = jsondecode(file("${path.module}/fsbp-controls-us-east-2.json"))
  # Preserve legacy all-on behavior while supporting explicit independent development stages.
  config_recording_enabled   = var.enable_collection || var.enable_config_recording
  cloudtrail_logging_enabled = var.enable_collection || var.enable_cloudtrail_logging
  cspm_standard_enabled      = var.enable_collection || var.enable_cspm_standard
}

# Refuse root sessions before resource creation, even inside the expected account.
# Stop unsafe identities before resource provisioning begins.
# Inputs: the referenced variables, policy or resource IDs. Outputs: this resource's managed state and exported attributes.
resource "terraform_data" "identity_guard" {
  input = data.aws_caller_identity.current.account_id
  lifecycle {
    precondition {
      condition     = !(var.enable_collection && (var.enable_config_recording || var.enable_cloudtrail_logging || var.enable_cspm_standard))
      error_message = "Choose legacy all-on or independent service switches, not both."
    }
    precondition {
      condition     = !local.cspm_standard_enabled || local.config_recording_enabled
      error_message = "The reviewed S3 CSPM instrument stage requires Config recording."
    }
    precondition {
      condition     = data.aws_caller_identity.current.account_id == local.account_id && startswith(data.aws_caller_identity.current.arn, "arn:aws:sts::653464153304:assumed-role/dissertation-paused-baseline-deploy/")
      error_message = "Use the bounded dissertation deployment role in account 653464153304."
    }
  }
}
