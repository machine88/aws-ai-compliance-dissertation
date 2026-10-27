# AWS owns the Config service-linked role's trust and read permissions.
# Create the AWS-managed service role required by Config.
# Inputs: the referenced variables, policy or resource IDs. Outputs: this resource's managed state and exported attributes.
resource "aws_iam_service_linked_role" "config" {
  aws_service_name = "config.amazonaws.com"
  description      = "Dissertation AWS Config recording role"
  depends_on       = [terraform_data.identity_guard]
}

# Type inclusion prevents automatic recording of every newly supported resource type.
# Recording still sees ALL S3 buckets in this region, including unrelated buckets.
# Select the resource types and role for Config recording.
# Inputs: the referenced variables, policy or resource IDs. Outputs: this resource's managed state and exported attributes.
resource "aws_config_configuration_recorder" "research" {
  name     = local.prefix
  role_arn = aws_iam_service_linked_role.config.arn
  recording_group {
    all_supported  = false
    resource_types = ["AWS::S3::Bucket"]
    recording_strategy {
      use_only = "INCLUSION_BY_RESOURCE_TYPES"
    }
  }
  recording_mode {
    recording_frequency = "CONTINUOUS"
  }
}

# Route Config deliveries to the protected telemetry bucket.
# Inputs: the referenced variables, policy or resource IDs. Outputs: this resource's managed state and exported attributes.
resource "aws_config_delivery_channel" "research" {
  name           = local.prefix
  s3_bucket_name = aws_s3_bucket.telemetry.id
  s3_key_prefix  = "config"
  snapshot_delivery_properties {
    delivery_frequency = "TwentyFour_Hours"
  }
  depends_on = [aws_config_configuration_recorder.research, aws_s3_bucket_policy.telemetry, aws_s3_bucket_versioning.telemetry, aws_s3_bucket_server_side_encryption_configuration.telemetry]
}

# Set the recorder to the explicitly requested collection state.
# Inputs: the referenced variables, policy or resource IDs. Outputs: this resource's managed state and exported attributes.
resource "aws_config_configuration_recorder_status" "research" {
  name       = aws_config_configuration_recorder.research.name
  is_enabled = var.enable_collection
  depends_on = [aws_config_delivery_channel.research]
}

# Direct Config rule evaluations are tagged to research buckets; CSPM uses its own service-linked rules.
# Define one research-tag-scoped AWS-managed compliance rule.
# Inputs: the referenced variables, policy or resource IDs. Outputs: this resource's managed state and exported attributes.
resource "aws_config_config_rule" "s3" {
  for_each = {
    tls_required         = "S3_BUCKET_SSL_REQUESTS_ONLY"
    public_access_blocks = "S3_BUCKET_LEVEL_PUBLIC_ACCESS_PROHIBITED"
  }
  name = "${local.prefix}-${replace(each.key, "_", "-")}"
  source {
    owner             = "AWS"
    source_identifier = each.value
  }
  # AWS rejects combining resource-type and tag scope; managed rule sources select S3.
  scope {
    tag_key   = "Project"
    tag_value = "aws-ai-compliance-dissertation"
  }
  depends_on = [aws_config_configuration_recorder.research]
}
