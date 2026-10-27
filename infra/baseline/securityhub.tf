# No default standards or automatically added controls: freeze the baseline explicitly.
# Enroll the account with default standards and automatic controls disabled.
# Inputs: the referenced variables, policy or resource IDs. Outputs: this resource's managed state and exported attributes.
resource "aws_securityhub_account" "research" {
  enable_default_standards  = false
  auto_enable_controls      = false
  control_finding_generator = "SECURITY_CONTROL"
  lifecycle {
    prevent_destroy = true
  }
  depends_on = [terraform_data.identity_guard, aws_config_configuration_recorder_status.research]
}

# Subscribing initially enables all standard controls before Terraform applies the manifest below.
# This transient account-wide evaluation and its potential cost must be approved before collection.
# Subscribe only when collection activation has been approved.
# Inputs: the referenced variables, policy or resource IDs. Outputs: this resource's managed state and exported attributes.
resource "aws_securityhub_standards_subscription" "fsbp" {
  count         = var.enable_collection ? 1 : 0
  standards_arn = local.fsbp_arn
  depends_on    = [aws_securityhub_account.research]
  lifecycle {
    precondition {
      condition     = local.fsbp.region == var.region && length(setsubtract(var.enabled_security_controls, toset(local.fsbp.control_ids))) == 0
      error_message = "Enabled controls must exist in the region-specific FSBP snapshot."
    }
  }
}

# Manage every available control from the snapshot, retaining only applicable instrument candidates.
# Set the explicit enabled/disabled state of each reviewed standard control.
# Inputs: the referenced variables, policy or resource IDs. Outputs: this resource's managed state and exported attributes.
resource "aws_securityhub_standards_control" "fsbp" {
  for_each              = var.enable_collection ? toset(local.fsbp.control_ids) : toset([])
  standards_control_arn = "${replace(aws_securityhub_standards_subscription.fsbp[0].id, "subscription/", "control/")}/${each.key}"
  control_status        = contains(var.enabled_security_controls, each.key) ? "ENABLED" : "DISABLED"
  disabled_reason       = contains(var.enabled_security_controls, each.key) ? null : "Outside initial dissertation S3 instrument scope"
}
