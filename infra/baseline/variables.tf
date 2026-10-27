# Ohio is the reviewed implementation region; expansion requires another plan review.
variable "region" {
  type    = string
  default = "us-east-2"
  validation {
    condition     = var.region == "us-east-2"
    error_message = "This baseline is scoped to us-east-2."
  }
}

variable "aws_profile" {
  type        = string
  default     = "dissertation"
  description = "Explicit local profile; the provider independently restricts its account."
}

# A deployed foundation can remain paused until the collection plan is approved.
variable "enable_collection" {
  type        = bool
  default     = false
  description = "Starts Config and CloudTrail and subscribes to the scoped CSPM standard."
}

variable "budget_email" {
  type        = string
  description = "User-selected destination for account-wide budget alerts; no address is assumed."
  validation {
    condition     = can(regex("^[^@[:space:]]+@[^@[:space:]]+[.][^@[:space:]]+$", var.budget_email))
    error_message = "Supply the reviewed budget-alert email address."
  }
}

# Planning value only; alerts are delayed notifications and do not stop charges.
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
variable "enabled_security_controls" {
  type    = set(string)
  default = ["S3.5", "S3.8"]
  validation {
    condition     = length(var.enabled_security_controls) > 0 && alltrue([for id in var.enabled_security_controls : contains(["S3.5", "S3.8"], id)])
    error_message = "Only the reviewed S3.5 and S3.8 instrument candidates are supported in this phase."
  }
}
