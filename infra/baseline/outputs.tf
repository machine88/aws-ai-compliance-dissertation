# Identifiers are configuration provenance, not experimental findings.
# Expose telemetry_bucket for verification and downstream tooling.
# Inputs: the referenced resource attribute or protocol value. Outputs: this named Terraform result.
output "telemetry_bucket" {
  value = aws_s3_bucket.telemetry.id
}
# Expose cloudtrail_arn for verification and downstream tooling.
# Inputs: the referenced resource attribute or protocol value. Outputs: this named Terraform result.
output "cloudtrail_arn" {
  value = aws_cloudtrail.research.arn
}
# Expose config_recorder for verification and downstream tooling.
# Inputs: the referenced resource attribute or protocol value. Outputs: this named Terraform result.
output "config_recorder" {
  value = aws_config_configuration_recorder.research.name
}
# Expose collection_enabled for verification and downstream tooling.
# Inputs: the referenced resource attribute or protocol value. Outputs: this named Terraform result.
output "collection_enabled" {
  value       = local.config_recording_enabled || local.cloudtrail_logging_enabled || local.cspm_standard_enabled
  description = "Any requested monitoring component is enabled; inspect the individual reviewed inputs for scope."
}
# Expose control_manifest_sha256 for verification and downstream tooling.
# Inputs: the referenced resource attribute or protocol value. Outputs: this named Terraform result.
output "control_manifest_sha256" {
  value = filesha256("${path.module}/fsbp-controls-us-east-2.json")
}
