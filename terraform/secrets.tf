locals {
  # Terraform-managed secrets. Other agent-cody/* secrets created out-of-band (e.g.
  # telegram-bot-token, future per-tenant secrets) are also IAM-permitted via the
  # wildcard in iam.tf gw policy — no need to list them here unless we want Terraform
  # to manage their lifecycle.
  secret_names = [
    "anthropic-api-key",
    "graph-msal-token-cache",
    "baileys-auth-dir", # legacy WhatsApp path; kept as placeholder for now
    "neo4j-password",
    "elevenlabs-api-key",
    "style-card",
    "graph-sender-frozen",
  ]
}

resource "aws_secretsmanager_secret" "cody" {
  for_each    = toset(local.secret_names)
  name        = "${local.name}/${each.key}"
  kms_key_id  = aws_kms_key.cmk.arn
  description = "Populated manually via scripts/populate-secrets.sh; DO NOT commit values"
  tags        = local.tags_data
}

resource "aws_secretsmanager_secret_version" "cody_placeholder" {
  for_each      = aws_secretsmanager_secret.cody
  secret_id     = each.value.id
  secret_string = jsonencode({ placeholder = true, populated_at = null })
  lifecycle {
    ignore_changes = [secret_string]
  }
}

output "secret_arns" {
  value     = { for k, v in aws_secretsmanager_secret.cody : k => v.arn }
  sensitive = false
}
