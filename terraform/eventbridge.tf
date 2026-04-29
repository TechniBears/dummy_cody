resource "aws_cloudwatch_event_rule" "morning_briefing" {
  name                = "${local.name}-morning-briefing"
  description         = "Daily briefing trigger; Phase 3 repoints target to Gateway /tools/invoke."
  schedule_expression = "cron(30 3 * * ? *)" # 03:30 UTC — operator converts to local
}

resource "aws_cloudwatch_event_rule" "style_card_refresh" {
  name                = "${local.name}-style-card-refresh"
  description         = "Weekly Sunday 03:00 UTC"
  schedule_expression = "cron(0 3 ? * SUN *)"
}

resource "aws_cloudwatch_event_rule" "audit_verifier" {
  name                = "${local.name}-audit-verifier"
  description         = "Daily 01:00 UTC audit log integrity check"
  schedule_expression = "cron(0 1 * * ? *)"
}

# --- targets ---
resource "aws_cloudwatch_event_target" "style_card_refresh" {
  rule      = aws_cloudwatch_event_rule.style_card_refresh.name
  target_id = "lambda"
  arn       = aws_lambda_function.style_card_refresh.arn
}

resource "aws_cloudwatch_event_target" "audit_verifier" {
  rule      = aws_cloudwatch_event_rule.audit_verifier.name
  target_id = "lambda"
  arn       = aws_lambda_function.audit_verifier.arn
}

# --- permissions ---
resource "aws_lambda_permission" "style_card_refresh_event" {
  statement_id  = "AllowEventBridge-style-card-refresh"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.style_card_refresh.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.style_card_refresh.arn
}

resource "aws_lambda_permission" "audit_verifier_event" {
  statement_id  = "AllowEventBridge-audit-verifier"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.audit_verifier.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.audit_verifier.arn
}
