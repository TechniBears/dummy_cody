data "aws_iam_policy_document" "ec2_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

data "aws_iam_policy_document" "lambda_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

# =================================================================
# Gateway EC2 instance role
# =================================================================
resource "aws_iam_role" "gw" {
  name               = "${local.name}-gw-role"
  assume_role_policy = data.aws_iam_policy_document.ec2_assume.json
  tags               = local.tags_gw
}

resource "aws_iam_role_policy_attachment" "gw_ssm" {
  role       = aws_iam_role.gw.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

data "aws_iam_policy_document" "gw_policy" {
  statement {
    sid     = "ReadSecrets"
    actions = ["secretsmanager:GetSecretValue", "secretsmanager:DescribeSecret"]
    # Wildcard over agent-cody/* namespace — covers Terraform-managed secrets AND
    # out-of-band ones (e.g. telegram-bot-token, future per-tenant tokens).
    resources = ["arn:aws:secretsmanager:${var.region}:${data.aws_caller_identity.current.account_id}:secret:agent-cody/*"]
  }

  statement {
    sid     = "DiscoverSecrets"
    actions = ["secretsmanager:ListSecrets"]
    # ListSecrets does not support resource-level permissions; "*" is the only
    # valid resource. Paired with the agent-cody/* Get/Describe scope above so
    # discovery works but reads still stay inside Cody's own namespace.
    resources = ["*"]
  }

  statement {
    sid       = "WriteBaileysAuth"
    actions   = ["secretsmanager:PutSecretValue"]
    resources = [aws_secretsmanager_secret.cody["baileys-auth-dir"].arn]
  }

  statement {
    sid       = "WriteGraphMsal"
    actions   = ["secretsmanager:PutSecretValue"]
    resources = [aws_secretsmanager_secret.cody["graph-msal-token-cache"].arn]
  }

  statement {
    sid       = "KMSDecrypt"
    actions   = ["kms:Decrypt", "kms:DescribeKey", "kms:GenerateDataKey"]
    resources = [aws_kms_key.cmk.arn]
  }

  statement {
    sid       = "AuditLogWrite"
    actions   = ["s3:PutObject", "s3:PutObjectRetention"]
    resources = ["${aws_s3_bucket.audit.arn}/*"]
    condition {
      test     = "StringEquals"
      variable = "s3:object-lock-mode"
      values   = ["COMPLIANCE"]
    }
    condition {
      test     = "NumericGreaterThanEquals"
      variable = "s3:object-lock-remaining-retention-days"
      values   = ["365"]
    }
  }

  statement {
    sid       = "DraftQueueWriteOnly"
    actions   = ["s3:PutObject", "s3:GetObject"]
    resources = ["${aws_s3_bucket.draft_queue.arn}/*"]
  }

  statement {
    sid       = "DraftQueueList"
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.draft_queue.arn]
  }

  statement {
    sid       = "OwnLogs"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents", "logs:CreateLogGroup"]
    resources = ["arn:aws:logs:${var.region}:${data.aws_caller_identity.current.account_id}:log-group:/agent-cody/*"]
  }

  statement {
    sid     = "BedrockInvokeClaude"
    actions = ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"]
    resources = [
      # Claude 4.5+ requires cross-region inference profiles (on-demand throughput not supported).
      "arn:aws:bedrock:${var.region}:${data.aws_caller_identity.current.account_id}:inference-profile/us.anthropic.claude-sonnet-4-6-*",
      "arn:aws:bedrock:${var.region}:${data.aws_caller_identity.current.account_id}:inference-profile/us.anthropic.claude-haiku-4-5-*",
      "arn:aws:bedrock:${var.region}:${data.aws_caller_identity.current.account_id}:inference-profile/us.anthropic.claude-*",
      # Foundation model ARNs still needed — inference profiles dispatch to these.
      "arn:aws:bedrock:*::foundation-model/anthropic.claude-sonnet-4-6-*",
      "arn:aws:bedrock:*::foundation-model/anthropic.claude-haiku-4-5-*",
      "arn:aws:bedrock:*::foundation-model/anthropic.claude-*",
    ]
  }

  statement {
    sid       = "BedrockDiscovery"
    actions   = ["bedrock:ListFoundationModels", "bedrock:ListInferenceProfiles"]
    resources = ["*"]
  }

  statement {
    sid = "BedrockMarketplaceSubscribe"
    actions = [
      "aws-marketplace:ViewSubscriptions",
      "aws-marketplace:Subscribe",
      "aws-marketplace:Unsubscribe",
    ]
    resources = ["*"]
  }

  statement {
    sid       = "BedrockInvokeTitanEmbeddings"
    actions   = ["bedrock:InvokeModel"]
    resources = ["arn:aws:bedrock:${var.region}::foundation-model/amazon.titan-embed-text-v2:*"]
  }
}

resource "aws_iam_policy" "gw" {
  name   = "${local.name}-gw-policy"
  policy = data.aws_iam_policy_document.gw_policy.json
}

resource "aws_iam_role_policy_attachment" "gw_custom" {
  role       = aws_iam_role.gw.name
  policy_arn = aws_iam_policy.gw.arn
}

resource "aws_iam_instance_profile" "gw" {
  name = "${local.name}-gw-profile"
  role = aws_iam_role.gw.name
}

# =================================================================
# Memory VM role (Neo4j) — minimal privs
# =================================================================
resource "aws_iam_role" "mem" {
  name               = "${local.name}-mem-role"
  assume_role_policy = data.aws_iam_policy_document.ec2_assume.json
  tags               = local.tags_mem
}

resource "aws_iam_role_policy_attachment" "mem_ssm" {
  role       = aws_iam_role.mem.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

data "aws_iam_policy_document" "mem_policy" {
  statement {
    sid       = "Neo4jPasswordOnly"
    actions   = ["secretsmanager:GetSecretValue", "secretsmanager:PutSecretValue", "secretsmanager:DescribeSecret"]
    resources = [aws_secretsmanager_secret.cody["neo4j-password"].arn]
  }

  statement {
    sid       = "KMSForNeo4jSecret"
    actions   = ["kms:Decrypt", "kms:GenerateDataKey", "kms:DescribeKey"]
    resources = [aws_kms_key.cmk.arn]
  }

  statement {
    sid       = "SelfWipeUserData"
    actions   = ["ec2:ModifyInstanceAttribute"]
    resources = ["*"]
    condition {
      test     = "StringEquals"
      variable = "ec2:ResourceTag/Component"
      values   = ["memory"]
    }
  }

  statement {
    sid       = "OwnLogs"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents", "logs:CreateLogGroup"]
    resources = ["arn:aws:logs:${var.region}:${data.aws_caller_identity.current.account_id}:log-group:/agent-cody/*"]
  }
}

resource "aws_iam_policy" "mem" {
  name   = "${local.name}-mem-policy"
  policy = data.aws_iam_policy_document.mem_policy.json
}

resource "aws_iam_role_policy_attachment" "mem_custom" {
  role       = aws_iam_role.mem.name
  policy_arn = aws_iam_policy.mem.arn
}

resource "aws_iam_instance_profile" "mem" {
  name = "${local.name}-mem-profile"
  role = aws_iam_role.mem.name
}

# =================================================================
# Lambda roles — per-function least-privilege
# =================================================================

# send-approval-dispatcher: draft-queue RW, audit, KMS
resource "aws_iam_role" "lambda_send_approval" {
  name               = "${local.name}-lambda-send-approval-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

resource "aws_iam_role_policy_attachment" "lambda_send_approval_basic" {
  role       = aws_iam_role.lambda_send_approval.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy_attachment" "lambda_send_approval_vpc" {
  role       = aws_iam_role.lambda_send_approval.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole"
}

data "aws_iam_policy_document" "lambda_send_approval" {
  statement {
    actions   = ["s3:PutObject", "s3:GetObject", "s3:ListBucket"]
    resources = [aws_s3_bucket.draft_queue.arn, "${aws_s3_bucket.draft_queue.arn}/*"]
  }
  statement {
    actions   = ["s3:PutObject", "s3:PutObjectRetention"]
    resources = ["${aws_s3_bucket.audit.arn}/*"]
    condition {
      test     = "StringEquals"
      variable = "s3:object-lock-mode"
      values   = ["COMPLIANCE"]
    }
  }
  statement {
    actions   = ["kms:Decrypt", "kms:GenerateDataKey"]
    resources = [aws_kms_key.cmk.arn]
  }
}

resource "aws_iam_role_policy" "lambda_send_approval" {
  role   = aws_iam_role.lambda_send_approval.id
  policy = data.aws_iam_policy_document.lambda_send_approval.json
}

# graph-sender: Graph send + Graph MSAL cache + audit + KMS + frozen flag check
resource "aws_iam_role" "lambda_graph_sender" {
  name               = "${local.name}-lambda-graph-sender-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

resource "aws_iam_role_policy_attachment" "lambda_graph_sender_basic" {
  role       = aws_iam_role.lambda_graph_sender.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy_attachment" "lambda_graph_sender_vpc" {
  role       = aws_iam_role.lambda_graph_sender.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole"
}

data "aws_iam_policy_document" "lambda_graph_sender" {
  statement {
    actions = ["secretsmanager:GetSecretValue"]
    resources = [
      aws_secretsmanager_secret.cody["graph-msal-token-cache"].arn,
      aws_secretsmanager_secret.cody["graph-sender-frozen"].arn,
    ]
  }
  statement {
    actions   = ["secretsmanager:PutSecretValue"]
    resources = [aws_secretsmanager_secret.cody["graph-msal-token-cache"].arn]
  }
  statement {
    actions   = ["s3:GetObject", "s3:PutObject"]
    resources = ["${aws_s3_bucket.draft_queue.arn}/*"]
  }
  statement {
    actions   = ["s3:PutObject", "s3:PutObjectRetention"]
    resources = ["${aws_s3_bucket.audit.arn}/*"]
    condition {
      test     = "StringEquals"
      variable = "s3:object-lock-mode"
      values   = ["COMPLIANCE"]
    }
  }
  statement {
    actions   = ["kms:Decrypt", "kms:GenerateDataKey"]
    resources = [aws_kms_key.cmk.arn]
  }
}

resource "aws_iam_role_policy" "lambda_graph_sender" {
  role   = aws_iam_role.lambda_graph_sender.id
  policy = data.aws_iam_policy_document.lambda_graph_sender.json
}

# style-card-refresh: Graph read + style-card secret write + audit
resource "aws_iam_role" "lambda_style_card" {
  name               = "${local.name}-lambda-style-card-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

resource "aws_iam_role_policy_attachment" "lambda_style_card_basic" {
  role       = aws_iam_role.lambda_style_card.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy_attachment" "lambda_style_card_vpc" {
  role       = aws_iam_role.lambda_style_card.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole"
}

data "aws_iam_policy_document" "lambda_style_card" {
  statement {
    actions = ["secretsmanager:GetSecretValue"]
    resources = [
      aws_secretsmanager_secret.cody["graph-msal-token-cache"].arn,
    ]
  }
  statement {
    actions   = ["secretsmanager:PutSecretValue"]
    resources = [aws_secretsmanager_secret.cody["style-card"].arn]
  }
  statement {
    actions   = ["s3:PutObject", "s3:PutObjectRetention"]
    resources = ["${aws_s3_bucket.audit.arn}/*"]
    condition {
      test     = "StringEquals"
      variable = "s3:object-lock-mode"
      values   = ["COMPLIANCE"]
    }
  }
  statement {
    actions   = ["kms:Decrypt", "kms:GenerateDataKey"]
    resources = [aws_kms_key.cmk.arn]
  }
  statement {
    sid     = "BedrockInvokeForStyleCard"
    actions = ["bedrock:InvokeModel"]
    resources = [
      "arn:aws:bedrock:${var.region}::foundation-model/anthropic.claude-haiku-4-5-*",
      "arn:aws:bedrock:${var.region}::foundation-model/anthropic.claude-sonnet-4-6-*",
    ]
  }
}

resource "aws_iam_role_policy" "lambda_style_card" {
  role   = aws_iam_role.lambda_style_card.id
  policy = data.aws_iam_policy_document.lambda_style_card.json
}

# audit-verifier: audit READ only, no write anywhere
resource "aws_iam_role" "lambda_audit_verifier" {
  name               = "${local.name}-lambda-audit-verifier-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

resource "aws_iam_role_policy_attachment" "lambda_audit_verifier_basic" {
  role       = aws_iam_role.lambda_audit_verifier.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy_attachment" "lambda_audit_verifier_vpc" {
  role       = aws_iam_role.lambda_audit_verifier.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole"
}

data "aws_iam_policy_document" "lambda_audit_verifier" {
  statement {
    actions   = ["s3:GetObject", "s3:ListBucket", "s3:GetObjectRetention"]
    resources = [aws_s3_bucket.audit.arn, "${aws_s3_bucket.audit.arn}/*"]
  }
  statement {
    actions   = ["sns:Publish"]
    resources = [aws_sns_topic.alerts.arn]
  }
  statement {
    actions   = ["kms:Decrypt"]
    resources = [aws_kms_key.cmk.arn]
  }
}

resource "aws_iam_role_policy" "lambda_audit_verifier" {
  role   = aws_iam_role.lambda_audit_verifier.id
  policy = data.aws_iam_policy_document.lambda_audit_verifier.json
}

# graph-sender-freeze: flip frozen flag + stop Gateway EC2 at budget breach
resource "aws_iam_role" "lambda_freeze" {
  name               = "${local.name}-lambda-freeze-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

resource "aws_iam_role_policy_attachment" "lambda_freeze_basic" {
  role       = aws_iam_role.lambda_freeze.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

data "aws_iam_policy_document" "lambda_freeze" {
  statement {
    actions   = ["secretsmanager:PutSecretValue", "secretsmanager:GetSecretValue"]
    resources = [aws_secretsmanager_secret.cody["graph-sender-frozen"].arn]
  }
  statement {
    actions   = ["ec2:StopInstances", "ec2:DescribeInstances"]
    resources = ["*"]
    condition {
      test     = "StringEquals"
      variable = "ec2:ResourceTag/Project"
      values   = ["agent-cody"]
    }
  }
  statement {
    actions   = ["kms:Decrypt", "kms:GenerateDataKey"]
    resources = [aws_kms_key.cmk.arn]
  }
  statement {
    actions   = ["sns:Publish"]
    resources = [aws_sns_topic.alerts.arn]
  }
}

resource "aws_iam_role_policy" "lambda_freeze" {
  role   = aws_iam_role.lambda_freeze.id
  policy = data.aws_iam_policy_document.lambda_freeze.json
}
