resource "aws_sns_topic" "alerts" {
  name              = "${local.name}-alerts"
  kms_master_key_id = aws_kms_key.cmk.id
}

resource "aws_sns_topic_subscription" "email" {
  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "email"
  endpoint  = var.alarm_email
}

# SMS subscription only when a real phone number is provided
resource "aws_sns_topic_subscription" "sms" {
  count     = var.alarm_phone != "+10000000000" ? 1 : 0
  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "sms"
  endpoint  = var.alarm_phone
}

# SMS spend cap: AWS account default is already $1/mo on new accounts — we don't need to
# set it explicitly. Requesting a higher limit requires a support ticket. Leaving as AWS default.

# ---------------- OpenClaw log group (14d retention — was 90d) ----------------
resource "aws_cloudwatch_log_group" "openclaw" {
  name              = "/agent-cody/openclaw"
  retention_in_days = 14
  kms_key_id        = aws_kms_key.cmk.arn
}

# Metric filters + security alarms (config.apply / system.run / MEDIA:/) deferred to Phase 1
# — nothing logs to /agent-cody/openclaw until OpenClaw actually runs.

# ---------------- Billing alarms — 50% / 80% / 100% ----------------
resource "aws_cloudwatch_metric_alarm" "billing_50pct" {
  alarm_name          = "${local.name}-billing-50pct"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = 1
  metric_name         = "EstimatedCharges"
  namespace           = "AWS/Billing"
  period              = 21600
  statistic           = "Maximum"
  threshold           = var.monthly_budget_usd * 0.5
  alarm_description   = "Monthly spend at 50% of ${var.monthly_budget_usd} USD budget"
  alarm_actions       = [aws_sns_topic.alerts.arn]
  dimensions          = { Currency = "USD" }
}

resource "aws_cloudwatch_metric_alarm" "billing_80pct" {
  alarm_name          = "${local.name}-billing-80pct"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = 1
  metric_name         = "EstimatedCharges"
  namespace           = "AWS/Billing"
  period              = 21600
  statistic           = "Maximum"
  threshold           = var.monthly_budget_usd * 0.8
  alarm_description   = "Monthly spend at 80% of ${var.monthly_budget_usd} USD budget. Freeze Lambda fires."
  alarm_actions = [
    aws_sns_topic.alerts.arn,
    aws_lambda_function.graph_sender_freeze.arn,
  ]
  dimensions = { Currency = "USD" }
}

resource "aws_cloudwatch_metric_alarm" "billing_100pct" {
  alarm_name          = "${local.name}-billing-100pct"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = 1
  metric_name         = "EstimatedCharges"
  namespace           = "AWS/Billing"
  period              = 21600
  statistic           = "Maximum"
  threshold           = var.monthly_budget_usd
  alarm_description   = "Monthly spend HIT ${var.monthly_budget_usd} USD budget cap"
  alarm_actions = [
    aws_sns_topic.alerts.arn,
    aws_lambda_function.graph_sender_freeze.arn,
  ]
  dimensions = { Currency = "USD" }
}

resource "aws_lambda_permission" "billing_80_invoke" {
  statement_id  = "AllowCloudWatchBilling80"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.graph_sender_freeze.function_name
  principal     = "lambda.alarms.cloudwatch.amazonaws.com"
  source_arn    = aws_cloudwatch_metric_alarm.billing_80pct.arn
}

resource "aws_lambda_permission" "billing_100_invoke" {
  statement_id  = "AllowCloudWatchBilling100"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.graph_sender_freeze.function_name
  principal     = "lambda.alarms.cloudwatch.amazonaws.com"
  source_arn    = aws_cloudwatch_metric_alarm.billing_100pct.arn
}
