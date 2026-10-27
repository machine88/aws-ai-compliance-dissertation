# Identifiers are configuration provenance, not experimental findings.
output "telemetry_bucket" {
  value = aws_s3_bucket.telemetry.id
}
output "cloudtrail_arn" {
  value = aws_cloudtrail.research.arn
}
output "config_recorder" {
  value = aws_config_configuration_recorder.research.name
}
output "collection_enabled" {
  value = var.enable_collection
}
output "control_manifest_sha256" {
  value = filesha256("${path.module}/fsbp-controls-us-east-2.json")
}
