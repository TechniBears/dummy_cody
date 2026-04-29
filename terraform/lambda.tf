data "archive_file" "send_approval_dispatcher" {
  type        = "zip"
  source_file = "${path.module}/../lambdas/send-approval-dispatcher/handler.py"
  output_path = "${path.module}/../lambdas/send-approval-dispatcher.zip"
}

data "archive_file" "graph_sender" {
  type        = "zip"
  source_file = "${path.module}/../lambdas/graph-sender/handler.py"
  output_path = "${path.module}/../lambdas/graph-sender.zip"
}

data "archive_file" "style_card_refresh" {
  type        = "zip"
  source_file = "${path.module}/../lambdas/style-card-refresh/handler.py"
  output_path = "${path.module}/../lambdas/style-card-refresh.zip"
}

data "archive_file" "audit_verifier" {
  type        = "zip"
  source_file = "${path.module}/../lambdas/audit-verifier/handler.py"
  output_path = "${path.module}/../lambdas/audit-verifier.zip"
}

data "archive_file" "graph_sender_freeze" {
  type        = "zip"
  source_file = "${path.module}/../lambdas/graph-sender-freeze/handler.py"
  output_path = "${path.module}/../lambdas/graph-sender-freeze.zip"
}

# ---------------- send-approval-dispatcher ----------------
resource "aws_lambda_function" "send_approval_dispatcher" {
  function_name    = "${local.name}-send-approval-dispatcher"
  role             = aws_iam_role.lambda_send_approval.arn
  handler          = "handler.handler"
  runtime          = "python3.12"
  filename         = data.archive_file.send_approval_dispatcher.output_path
  source_code_hash = data.archive_file.send_approval_dispatcher.output_base64sha256
  timeout          = 30
  memory_size      = 512

  reserved_concurrent_executions = 10

  vpc_config {
    subnet_ids         = [for s in aws_subnet.private : s.id]
    security_group_ids = [aws_security_group.lambda.id]
  }

  environment {
    variables = {
      AUDIT_BUCKET       = aws_s3_bucket.audit.id
      DRAFT_QUEUE_BUCKET = aws_s3_bucket.draft_queue.id
      REGION             = var.region
    }
  }

  tracing_config { mode = "Active" }

  tags = { Component = "lambda" }
}

# ---------------- graph-sender ----------------
resource "aws_lambda_function" "graph_sender" {
  function_name    = "${local.name}-graph-sender"
  role             = aws_iam_role.lambda_graph_sender.arn
  handler          = "handler.handler"
  runtime          = "python3.12"
  filename         = data.archive_file.graph_sender.output_path
  source_code_hash = data.archive_file.graph_sender.output_base64sha256
  timeout          = 60
  memory_size      = 512

  reserved_concurrent_executions = 5

  vpc_config {
    subnet_ids         = [for s in aws_subnet.private : s.id]
    security_group_ids = [aws_security_group.lambda.id]
  }

  environment {
    variables = {
      AUDIT_BUCKET       = aws_s3_bucket.audit.id
      DRAFT_QUEUE_BUCKET = aws_s3_bucket.draft_queue.id
      REGION             = var.region
      GRAPH_MSAL_SECRET  = aws_secretsmanager_secret.cody["graph-msal-token-cache"].name
      FROZEN_FLAG_SECRET = aws_secretsmanager_secret.cody["graph-sender-frozen"].name
    }
  }

  tracing_config { mode = "Active" }

  tags = { Component = "lambda" }
}

# ---------------- style-card-refresh ----------------
resource "aws_lambda_function" "style_card_refresh" {
  function_name    = "${local.name}-style-card-refresh"
  role             = aws_iam_role.lambda_style_card.arn
  handler          = "handler.handler"
  runtime          = "python3.12"
  filename         = data.archive_file.style_card_refresh.output_path
  source_code_hash = data.archive_file.style_card_refresh.output_base64sha256
  timeout          = 300
  memory_size      = 1024

  reserved_concurrent_executions = 2

  vpc_config {
    subnet_ids         = [for s in aws_subnet.private : s.id]
    security_group_ids = [aws_security_group.lambda.id]
  }

  environment {
    variables = {
      AUDIT_BUCKET      = aws_s3_bucket.audit.id
      REGION            = var.region
      GRAPH_MSAL_SECRET = aws_secretsmanager_secret.cody["graph-msal-token-cache"].name
      STYLE_CARD_SECRET = aws_secretsmanager_secret.cody["style-card"].name
    }
  }

  tracing_config { mode = "Active" }

  tags = { Component = "lambda" }
}

# ---------------- audit-verifier ----------------
resource "aws_lambda_function" "audit_verifier" {
  function_name    = "${local.name}-audit-verifier"
  role             = aws_iam_role.lambda_audit_verifier.arn
  handler          = "handler.handler"
  runtime          = "python3.12"
  filename         = data.archive_file.audit_verifier.output_path
  source_code_hash = data.archive_file.audit_verifier.output_base64sha256
  timeout          = 300
  memory_size      = 1024

  reserved_concurrent_executions = 2

  vpc_config {
    subnet_ids         = [for s in aws_subnet.private : s.id]
    security_group_ids = [aws_security_group.lambda.id]
  }

  environment {
    variables = {
      AUDIT_BUCKET = aws_s3_bucket.audit.id
      REGION       = var.region
      SNS_TOPIC    = aws_sns_topic.alerts.arn
    }
  }

  tracing_config { mode = "Active" }

  tags = { Component = "lambda" }
}

# ---------------- graph-sender-freeze ----------------
resource "aws_lambda_function" "graph_sender_freeze" {
  function_name    = "${local.name}-graph-sender-freeze"
  role             = aws_iam_role.lambda_freeze.arn
  handler          = "handler.handler"
  runtime          = "python3.12"
  filename         = data.archive_file.graph_sender_freeze.output_path
  source_code_hash = data.archive_file.graph_sender_freeze.output_base64sha256
  timeout          = 60
  memory_size      = 256

  reserved_concurrent_executions = 2

  environment {
    variables = {
      REGION             = var.region
      FROZEN_FLAG_SECRET = aws_secretsmanager_secret.cody["graph-sender-frozen"].name
      GW_INSTANCE_ID     = aws_instance.gw.id
      SNS_TOPIC          = aws_sns_topic.alerts.arn
    }
  }

  tracing_config { mode = "Active" }

  tags = { Component = "lambda" }
}

# ---------------- Log groups ----------------
resource "aws_cloudwatch_log_group" "lambda" {
  for_each = toset([
    "send-approval-dispatcher",
    "graph-sender",
    "style-card-refresh",
    "audit-verifier",
    "graph-sender-freeze",
  ])
  name              = "/aws/lambda/${local.name}-${each.key}"
  retention_in_days = 30
  kms_key_id        = aws_kms_key.cmk.arn
}
