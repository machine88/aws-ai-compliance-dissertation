# Management events support scenario timing; data events and Insights are excluded from this phase.
# Configure the regional trail and its reviewed collection state.
# Inputs: the referenced variables, policy or resource IDs. Outputs: this resource's managed state and exported attributes.
resource "aws_cloudtrail" "research" {
  name                          = local.prefix
  s3_bucket_name                = aws_s3_bucket.telemetry.id
  s3_key_prefix                 = "cloudtrail"
  is_multi_region_trail         = false
  include_global_service_events = true
  enable_log_file_validation    = true
  enable_logging                = var.enable_collection
  event_selector {
    read_write_type           = "All"
    include_management_events = true
  }
  depends_on = [aws_s3_bucket_policy.telemetry, aws_s3_bucket_versioning.telemetry, aws_s3_bucket_server_side_encryption_configuration.telemetry]
}
