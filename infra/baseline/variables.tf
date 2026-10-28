# Ohio is the reviewed implementation region; expansion requires another plan review.
# Declare and validate the region input.
# Inputs: caller-supplied value or stated default. Outputs: a validated value for the configuration.
variable "region" {
  type    = string
  default = "us-east-2"
  validation {
    condition     = var.region == "us-east-2"
    error_message = "This baseline is scoped to us-east-2."
  }
}

# Declare and validate the aws_profile input.
# Inputs: caller-supplied value or stated default. Outputs: a validated value for the configuration.
variable "aws_profile" {
  type        = string
  default     = "dissertation"
  description = "Explicit local profile; the provider independently restricts its account."
}

# A deployed foundation can remain paused until the collection plan is approved.
# Declare and validate the enable_collection input.
# Inputs: caller-supplied value or stated default. Outputs: a validated value for the configuration.
variable "enable_collection" {
  type        = bool
  default     = false
  description = "Compatibility switch for all monitoring components; do not combine with independent switches. Requires an approved activation plan."
}

# Inputs: explicit reviewed service requests. Outputs: independent activation intent; defaults stay paused.
variable "enable_config_recording" {
  type        = bool
  default     = false
  nullable    = false
  description = "Request Config recording only; requires a separately approved activation plan."
}

# Input: explicit reviewed logging request. Output: management-trail activation intent, not CSPM enrollment.
variable "enable_cloudtrail_logging" {
  type        = bool
  default     = false
  nullable    = false
  description = "Request CloudTrail logging independently; does not authorize data events or collection."
}

# Input: explicit reviewed standard request. Output: CSPM subscription/control intent, requiring Config.
variable "enable_cspm_standard" {
  type        = bool
  default     = false
  nullable    = false
  description = "Request the existing reviewed CSPM standard/control manifest; requires Config recording and explicit cost/scope approval."
}

# Declare and validate the budget_email input.
# Inputs: caller-supplied value or stated default. Outputs: a validated value for the configuration.
variable "budget_email" {
  type        = string
  description = "User-selected destination for account-wide budget alerts; no address is assumed."
  validation {
    condition     = can(regex("^[^@[:space:]]+@[^@[:space:]]+[.][^@[:space:]]+$", var.budget_email))
    error_message = "Supply the reviewed budget-alert email address."
  }
}

# Planning value only; alerts are delayed notifications and do not stop charges.
# Declare and validate the monthly_budget_usd input.
# Inputs: caller-supplied value or stated default. Outputs: a validated value for the configuration.
variable "monthly_budget_usd" {
  type        = number
  default     = 100
  description = "Proposed monthly account-wide alert budget, subject to user approval."
  validation {
    condition     = var.monthly_budget_usd > 0
    error_message = "The monthly budget must be positive."
  }
}

# These two S3 controls are instrument candidates, not a frozen scenario catalog.
# Declare and validate the enabled_security_controls input.
# Inputs: caller-supplied value or stated default. Outputs: a validated value for the configuration.
variable "enabled_security_controls" {
  type    = set(string)
  default = ["S3.5", "S3.8"]
  validation {
    condition     = length(var.enabled_security_controls) > 0 && alltrue([for id in var.enabled_security_controls : contains(["S3.5", "S3.8"], id)])
    error_message = "Only the reviewed S3.5 and S3.8 instrument candidates are supported in this phase."
  }
}
