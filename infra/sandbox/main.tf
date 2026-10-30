# Development scenario storage only; no deployment or injection is authorized by this module.
# Inputs: pinned tool/provider versions and a separately reviewed backend configuration.
# Outputs: an isolated Terraform root; CI initializes with backend access disabled.
terraform {
  required_version = "~> 1.15.0"
  required_providers {
    aws = { source = "hashicorp/aws", version = "= 6.36.0" }
  }
  backend "s3" {
    bucket               = "dissertation-653464153304-us-east-2-state"
    key                  = "dissertation/653464153304/us-east-2/development-sandbox/terraform.tfstate"
    region               = "us-east-2"
    profile              = "dissertation"
    allowed_account_ids  = ["653464153304"]
    encrypt              = true
    use_lockfile         = true
    workspace_key_prefix = "dissertation/653464153304/us-east-2/development-sandbox/workspaces"
    assume_role = {
      role_arn     = "arn:aws:iam::653464153304:role/dissertation-sandbox-deploy"
      session_name = "dissertation-sandbox-state"
    }
  }
}

# Inputs: existing local login and bounded deployment role. Outputs: an Ohio-only provider.
# Current role/state permissions do not cover this root; review changes before a live plan.
provider "aws" {
  profile             = "dissertation"
  region              = "us-east-2"
  allowed_account_ids = ["653464153304"]
  assume_role {
    role_arn     = "arn:aws:iam::653464153304:role/dissertation-sandbox-deploy"
    session_name = "dissertation-sandbox-deploy"
  }
  default_tags {
    tags = {
      Project   = "aws-ai-compliance-dissertation"
      ManagedBy = "Terraform"
      Phase     = "development"
      Purpose   = "scenario-sandbox"
    }
  }
}

# Input: explicit opt-in after reviewing a real saved plan. Output: creation intent, off by default.
variable "create_sandbox" {
  type        = bool
  default     = false
  description = "Request dedicated development storage; a code merge is not deployment approval."
}

# Input: independent review-manifest hash, not the hash of a plan that contains this variable.
# Output: provenance retained with the guard; hash syntax alone never proves human approval.
variable "deployment_review_sha256" {
  type        = string
  default     = null
  description = "SHA-256 of the separately retained deployment review manifest."
  validation {
    condition     = var.deployment_review_sha256 == null || can(regex("^[a-f0-9]{64}$", var.deployment_review_sha256))
    error_message = "Supply a lowercase SHA-256 review fingerprint or leave creation disabled."
  }
}

# Input: selected provider session. Output: actual identity for fail-closed role checks.
data "aws_caller_identity" "current" {}

# Inputs: fixed study scope and creation intent. Outputs: one reserved name and a zero/one count.
locals {
  count       = var.create_sandbox ? 1 : 0
  account_id  = "653464153304"
  bucket_name = "dissertation-sandbox-653464153304-us-east-2-s3-01"
}

# Inputs: actual caller, workspace and review reference. Output: guard before any bucket write.
resource "terraform_data" "scope_guard" {
  count = local.count
  input = var.deployment_review_sha256
  lifecycle {
    precondition {
      condition     = data.aws_caller_identity.current.account_id == local.account_id && startswith(data.aws_caller_identity.current.arn, "arn:aws:sts::653464153304:assumed-role/dissertation-sandbox-deploy/") && terraform.workspace == "default"
      error_message = "Use the bounded dissertation deployment role and the isolated default workspace."
    }
    precondition {
      condition     = var.deployment_review_sha256 != null
      error_message = "Creation requires an independent review reference plus separate human approval of the saved plan."
    }
  }
}

# Inputs: reserved development name and guard. Output: separate empty storage, never adopted logs/state.
# Destruction requires an explicit source change/review; forced deletion is never requested.
resource "aws_s3_bucket" "sandbox" {
  count         = local.count
  bucket        = local.bucket_name
  force_destroy = false
  lifecycle { prevent_destroy = true }
  depends_on = [terraform_data.scope_guard]
}

# Input: dedicated bucket. Output: all four public-access protections retained during future checks.
resource "aws_s3_bucket_public_access_block" "sandbox" {
  count                   = local.count
  bucket                  = aws_s3_bucket.sandbox[0].id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Input: dedicated bucket. Output: owner-enforced access with ACLs disabled.
resource "aws_s3_bucket_ownership_controls" "sandbox" {
  count  = local.count
  bucket = aws_s3_bucket.sandbox[0].id
  rule { object_ownership = "BucketOwnerEnforced" }
}

# Input: dedicated empty bucket. Output: secure versioning baseline; no mutation loop or ignore_changes.
# A separately approved future check must restore Enabled and verify actual state before reuse.
resource "aws_s3_bucket_versioning" "sandbox" {
  count  = local.count
  bucket = aws_s3_bucket.sandbox[0].id
  versioning_configuration { status = "Enabled" }
}

# Input: dedicated bucket. Output: explicit SSE-S3 encryption and an SSE-C write block; no new KMS key.
resource "aws_s3_bucket_server_side_encryption_configuration" "sandbox" {
  count  = local.count
  bucket = aws_s3_bucket.sandbox[0].id
  rule {
    blocked_encryption_types = ["SSE-C"]
    bucket_key_enabled       = false
    apply_server_side_encryption_by_default { sse_algorithm = "AES256" }
  }
}

# Input: exact bucket/object ARNs. Output: transport denial only; no public or service write grants.
resource "aws_s3_bucket_policy" "sandbox" {
  count  = local.count
  bucket = aws_s3_bucket.sandbox[0].id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "RequireTLS"
      Effect    = "Deny"
      Principal = "*"
      Action    = "s3:*"
      Resource  = [aws_s3_bucket.sandbox[0].arn, "${aws_s3_bucket.sandbox[0].arn}/*"]
      Condition = { Bool = { "aws:SecureTransport" = "false" } }
    }]
  })
  depends_on = [aws_s3_bucket_public_access_block.sandbox, aws_s3_bucket_ownership_controls.sandbox]
}

# Input: resource creation intent. Output: exact target name or null, never credentials or trial data.
output "sandbox_bucket_name" {
  value = var.create_sandbox ? aws_s3_bucket.sandbox[0].bucket : null
}
