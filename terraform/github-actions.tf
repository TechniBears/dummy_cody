variable "enable_github_bundle_publish_role" {
  type        = bool
  description = "When true, create a GitHub OIDC role that can publish gateway deploy bundles to S3."
  default     = false
}

variable "github_bundle_publish_branch" {
  type        = string
  description = "Git branch allowed to assume the GitHub OIDC publish role."
  default     = "main"
}

data "tls_certificate" "github_actions_oidc" {
  count = var.enable_github_bundle_publish_role ? 1 : 0
  url   = "https://token.actions.githubusercontent.com"
}

locals {
  github_actions_thumbprint = var.enable_github_bundle_publish_role ? data.tls_certificate.github_actions_oidc[0].certificates[length(data.tls_certificate.github_actions_oidc[0].certificates) - 1].sha1_fingerprint : null
}

resource "aws_iam_openid_connect_provider" "github_actions" {
  count = var.enable_github_bundle_publish_role ? 1 : 0

  url = "https://token.actions.githubusercontent.com"

  client_id_list = [
    "sts.amazonaws.com",
  ]

  thumbprint_list = [
    local.github_actions_thumbprint,
  ]
}

data "aws_iam_policy_document" "github_bundle_publish_assume" {
  count = var.enable_github_bundle_publish_role ? 1 : 0

  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github_actions[0].arn]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:sub"
      values   = ["repo:${var.github_org_repo}:ref:refs/heads/${var.github_bundle_publish_branch}"]
    }
  }
}

resource "aws_iam_role" "github_bundle_publish" {
  count = var.enable_github_bundle_publish_role ? 1 : 0

  name               = "${local.name}-github-bundle-publish-role"
  assume_role_policy = data.aws_iam_policy_document.github_bundle_publish_assume[0].json
  tags               = { Name = "${local.name}-github-bundle-publish-role", Component = "ci" }
}

data "aws_iam_policy_document" "github_bundle_publish" {
  count = var.enable_github_bundle_publish_role ? 1 : 0

  statement {
    sid = "PublishGatewayBundles"
    actions = [
      "s3:PutObject",
      "s3:GetObject",
    ]
    resources = [
      "${aws_s3_bucket.draft_queue.arn}/bootstrap/deploy-bundles/*",
    ]
  }

  statement {
    sid = "ListBundlePrefix"
    actions = [
      "s3:ListBucket",
    ]
    resources = [
      aws_s3_bucket.draft_queue.arn,
    ]
    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values   = ["bootstrap/deploy-bundles/*"]
    }
  }

  # The draft_queue bucket is SSE-KMS with the project CMK, so PutObject /
  # GetObject require permission on the key itself; without this, uploads
  # fail with AccessDenied on kms:GenerateDataKey even when the S3 policy
  # is correct.
  statement {
    sid = "DraftQueueCMKAccess"
    actions = [
      "kms:GenerateDataKey",
      "kms:Decrypt",
    ]
    resources = [aws_kms_key.cmk.arn]
  }

  # Auto-deploy: after uploading the bundle, the CI job triggers
  # `cody-admin --pull-latest` on the gateway via SSM RunShellScript. Scoped
  # tightly to one instance + one document so this role can't run arbitrary
  # commands anywhere else.
  statement {
    sid = "SendCommandToGateway"
    actions = [
      "ssm:SendCommand",
    ]
    resources = [
      aws_instance.gw.arn,
      "arn:aws:ssm:${data.aws_region.current.name}::document/AWS-RunShellScript",
    ]
  }

  # Needed to poll the SendCommand result and surface success/failure in the
  # GitHub Actions run. Command IDs are ephemeral and unique, so scoping to
  # "*" is the standard pattern (and IAM doesn't offer a tighter knob here).
  statement {
    sid = "ReadCommandInvocations"
    actions = [
      "ssm:GetCommandInvocation",
      "ssm:ListCommandInvocations",
    ]
    resources = ["*"]
  }

  # Let the workflow resolve the gateway instance ID by Name tag instead of
  # hardcoding it — survives instance replacement.
  statement {
    sid = "DescribeGatewayInstance"
    actions = [
      "ec2:DescribeInstances",
    ]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "github_bundle_publish" {
  count = var.enable_github_bundle_publish_role ? 1 : 0

  name   = "${local.name}-github-bundle-publish"
  role   = aws_iam_role.github_bundle_publish[0].id
  policy = data.aws_iam_policy_document.github_bundle_publish[0].json
}

output "github_bundle_publish_role_arn" {
  value       = var.enable_github_bundle_publish_role ? aws_iam_role.github_bundle_publish[0].arn : ""
  description = "Role ARN for the GitHub Actions bundle publish workflow."
}
