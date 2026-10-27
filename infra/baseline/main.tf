# Regional monitoring baseline. Applying this configuration requires separate user approval.
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
  }
}

# Never resolve credentials from an implicit default profile or another AWS account.
provider "aws" {
  region              = var.region
  profile             = var.aws_profile
  allowed_account_ids = ["653464153304"]
  default_tags {
    tags = {
      Project   = "aws-ai-compliance-dissertation"
      ManagedBy = "Terraform"
      Phase     = "baseline"
    }
  }
}

# Billing is global and uses the Northern Virginia API endpoint.
provider "aws" {
  alias               = "billing"
  region              = "us-east-1"
  profile             = var.aws_profile
  allowed_account_ids = ["653464153304"]
}

data "aws_caller_identity" "current" {}

locals {
  account_id = "653464153304"
  prefix     = "dissertation-research"
  log_bucket = "${local.prefix}-${local.account_id}-${var.region}-logs"
  trail_arn  = "arn:aws:cloudtrail:${var.region}:${local.account_id}:trail/${local.prefix}"
  fsbp_arn   = "arn:aws:securityhub:${var.region}::standards/aws-foundational-security-best-practices/v/1.0.0"
  fsbp       = jsondecode(file("${path.module}/fsbp-controls-us-east-2.json"))
}

# Refuse root sessions before resource creation, even inside the expected account.
resource "terraform_data" "identity_guard" {
  input = data.aws_caller_identity.current.account_id
  lifecycle {
    precondition {
      condition     = data.aws_caller_identity.current.account_id == local.account_id && !endswith(data.aws_caller_identity.current.arn, ":root")
      error_message = "Use a non-root identity in dissertation account 653464153304."
    }
  }
}
