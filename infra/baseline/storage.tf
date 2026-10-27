# Dedicated evidence storage; existing application buckets are never adopted or modified.
resource "aws_s3_bucket" "telemetry" {
  bucket        = local.log_bucket
  force_destroy = false
  lifecycle {
    prevent_destroy = true
  }
  depends_on = [terraform_data.identity_guard]
}

resource "aws_s3_bucket_public_access_block" "telemetry" {
  bucket                  = aws_s3_bucket.telemetry.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_ownership_controls" "telemetry" {
  bucket = aws_s3_bucket.telemetry.id
  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_versioning" "telemetry" {
  bucket = aws_s3_bucket.telemetry.id
  versioning_configuration {
    status = "Enabled"
  }
}

# SSE-S3 avoids an extra KMS key fee; no evidence expiration is configured.
resource "aws_s3_bucket_server_side_encryption_configuration" "telemetry" {
  bucket = aws_s3_bucket.telemetry.id
  rule {
    # Preserve the block on customer-provided encryption keys for state and logs.
    blocked_encryption_types = ["SSE-C"]
    bucket_key_enabled       = false
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# Service writes are restricted to this account, region and delivery prefixes.
resource "aws_s3_bucket_policy" "telemetry" {
  bucket = aws_s3_bucket.telemetry.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "RequireTLS", Effect = "Deny", Principal = "*", Action = "s3:*"
        Resource  = [aws_s3_bucket.telemetry.arn, "${aws_s3_bucket.telemetry.arn}/*"]
        Condition = { Bool = { "aws:SecureTransport" = "false" } }
      },
      {
        Sid       = "CloudTrailAclCheck", Effect = "Allow", Principal = { Service = "cloudtrail.amazonaws.com" }
        Action    = "s3:GetBucketAcl", Resource = aws_s3_bucket.telemetry.arn
        Condition = { StringEquals = { "aws:SourceArn" = local.trail_arn } }
      },
      {
        Sid       = "CloudTrailDelivery", Effect = "Allow", Principal = { Service = "cloudtrail.amazonaws.com" }
        Action    = "s3:PutObject", Resource = "${aws_s3_bucket.telemetry.arn}/cloudtrail/AWSLogs/${local.account_id}/*"
        Condition = { StringEquals = { "aws:SourceArn" = local.trail_arn, "s3:x-amz-acl" = "bucket-owner-full-control" } }
      },
      {
        Sid    = "ConfigBucketCheck", Effect = "Allow", Principal = { Service = "config.amazonaws.com" }
        Action = ["s3:GetBucketAcl", "s3:ListBucket"], Resource = aws_s3_bucket.telemetry.arn
        Condition = {
          StringEquals = { "aws:SourceAccount" = local.account_id }
          ArnLike      = { "aws:SourceArn" = "arn:aws:config:${var.region}:${local.account_id}:*" }
        }
      },
      {
        Sid    = "ConfigDelivery", Effect = "Allow", Principal = { Service = "config.amazonaws.com" }
        Action = "s3:PutObject", Resource = "${aws_s3_bucket.telemetry.arn}/config/AWSLogs/${local.account_id}/Config/*"
        Condition = {
          StringEquals = { "aws:SourceAccount" = local.account_id, "s3:x-amz-acl" = "bucket-owner-full-control" }
          ArnLike      = { "aws:SourceArn" = "arn:aws:config:${var.region}:${local.account_id}:*" }
        }
      }
    ]
  })
  depends_on = [aws_s3_bucket_public_access_block.telemetry, aws_s3_bucket_ownership_controls.telemetry]
}
