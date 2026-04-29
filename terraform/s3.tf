# ---------- Audit bucket: Object Lock Compliance 1y, SSE-KMS, versioned ----------
resource "aws_s3_bucket" "audit" {
  bucket              = "${local.name}-audit-${data.aws_caller_identity.current.account_id}"
  object_lock_enabled = true
  tags                = local.tags_data
}

resource "aws_s3_bucket_versioning" "audit" {
  bucket = aws_s3_bucket.audit.id
  versioning_configuration { status = "Enabled" }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "audit" {
  bucket = aws_s3_bucket.audit.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = aws_kms_key.cmk.arn
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_public_access_block" "audit" {
  bucket                  = aws_s3_bucket.audit.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_object_lock_configuration" "audit" {
  bucket = aws_s3_bucket.audit.id
  rule {
    default_retention {
      mode = "COMPLIANCE"
      days = 365
    }
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "audit" {
  bucket = aws_s3_bucket.audit.id
  rule {
    id     = "ia-transition-90d"
    status = "Enabled"
    filter {}
    transition {
      days          = 90
      storage_class = "STANDARD_IA"
    }
    noncurrent_version_transition {
      noncurrent_days = 30
      storage_class   = "STANDARD_IA"
    }
  }
}

# ---------- Draft queue: SSE-KMS, versioned, 30d lifecycle ----------
resource "aws_s3_bucket" "draft_queue" {
  bucket = "${local.name}-draft-queue-${data.aws_caller_identity.current.account_id}"
  tags   = local.tags_data
}

resource "aws_s3_bucket_versioning" "draft_queue" {
  bucket = aws_s3_bucket.draft_queue.id
  versioning_configuration { status = "Enabled" }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "draft_queue" {
  bucket = aws_s3_bucket.draft_queue.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = aws_kms_key.cmk.arn
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_public_access_block" "draft_queue" {
  bucket                  = aws_s3_bucket.draft_queue.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_lifecycle_configuration" "draft_queue" {
  bucket = aws_s3_bucket.draft_queue.id
  rule {
    id     = "expire-old-drafts"
    status = "Enabled"
    filter {}
    expiration { days = 30 }
    noncurrent_version_expiration { noncurrent_days = 7 }
  }
}
