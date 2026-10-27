# Account-wide alerts also catch spend that cannot be allocated reliably by resource tag.
resource "aws_budgets_budget" "research" {
  provider     = aws.billing
  name         = "${local.prefix}-account-alerts"
  budget_type  = "COST"
  limit_amount = tostring(var.monthly_budget_usd)
  limit_unit   = "USD"
  time_unit    = "MONTHLY"
  dynamic "notification" {
    for_each = { actual_50 = { type = "ACTUAL", value = 50 }, actual_80 = { type = "ACTUAL", value = 80 }, actual_100 = { type = "ACTUAL", value = 100 }, forecast_100 = { type = "FORECASTED", value = 100 } }
    content {
      comparison_operator        = "GREATER_THAN"
      threshold                  = notification.value.value
      threshold_type             = "PERCENTAGE"
      notification_type          = notification.value.type
      subscriber_email_addresses = [var.budget_email]
    }
  }
  depends_on = [terraform_data.identity_guard]
}
