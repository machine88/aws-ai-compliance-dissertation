# Foundation only: no AWS resources declared. Complete after proposal and inventory review.
terraform {
  required_version = ">= 1.10, < 2.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
  # Supply the isolated state location during initialization.
  backend "s3" {}
}
variable "region" {
  type = string
  description = "Region selected in the reviewed deployment plan; no implicit default."
}
# Restrict provider operations to the dissertation account.
provider "aws" {
  region = var.region
  allowed_account_ids = ["653464153304"]
  default_tags {
    tags = {
      Project = "aws-ai-compliance-dissertation"
      ManagedBy = "Terraform"
    }
  }
}
