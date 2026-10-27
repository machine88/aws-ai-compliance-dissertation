# Bootstrap state is local until this protected bucket exists and its state is migrated.
terraform {
  required_version = ">= 1.10, < 2.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "= 6.36.0"
    }
  }
  backend "local" {
    path = "bootstrap.tfstate"
  }
}

provider "aws" {
  region              = "us-east-2"
  profile             = "dissertation"
  allowed_account_ids = ["653464153304"]
  default_tags {
    tags = { Project = "aws-ai-compliance-dissertation", ManagedBy = "Terraform", Phase = "bootstrap" }
  }
}

data "aws_caller_identity" "current" {}

# Root cannot provision state storage even in the correct account.
resource "terraform_data" "identity_guard" {
  input = data.aws_caller_identity.current.account_id
  lifecycle {
    precondition {
      condition     = data.aws_caller_identity.current.account_id == "653464153304" && !endswith(data.aws_caller_identity.current.arn, ":root")
      error_message = "Use a non-root identity in account 653464153304."
    }
  }
}

resource "aws_s3_bucket" "state" {
  bucket        = "dissertation-653464153304-us-east-2-state"
  force_destroy = false
  lifecycle {
    prevent_destroy = true
  }
  depends_on = [terraform_data.identity_guard]
}

resource "aws_s3_bucket_public_access_block" "state" {
  bucket                  = aws_s3_bucket.state.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_ownership_controls" "state" {
  bucket = aws_s3_bucket.state.id
  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_versioning" "state" {
  bucket = aws_s3_bucket.state.id
  versioning_configuration {
    status = "Enabled"
  }
}

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

output "state_bucket" {
  value = aws_s3_bucket.state.id
}
