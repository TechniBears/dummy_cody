variable "region" {
  type    = string
  default = "us-east-1"
}

variable "name_prefix" {
  type    = string
  default = "agent-cody"
}

variable "vpc_cidr" {
  type    = string
  default = "10.40.0.0/16"
}

variable "gw_instance_type" {
  type        = string
  description = "EC2 instance type for the Gateway VM. g4dn.2xlarge (8 vCPU, 32 GB, 1x NVIDIA T4 16 GB VRAM). Upgraded 2026-04-24 from t3.large after the Running-On-Demand-G-and-VT-instances quota (L-DB2E81BA) was raised to 32 vCPUs."
  default     = "g4dn.2xlarge"
}

variable "mem_instance_type" {
  type        = string
  description = "EC2 instance type for the Neo4j memory VM"
  default     = "t3.small"
}

variable "user_wa_number" {
  type        = string
  description = "Owner's WhatsApp number in E.164 format without the plus, e.g. 971501234567"
  sensitive   = true
}

variable "alarm_email" {
  type        = string
  description = "Email address for SNS alarm delivery"
}

variable "alarm_phone" {
  type        = string
  description = "Phone number in E.164 for SNS SMS alarm delivery (e.g. +971501234567). Leave as +10000000000 to skip SMS."
  default     = "+10000000000"
}

variable "monthly_budget_usd" {
  type        = number
  default     = 400
  description = "Hard budget alarm threshold"
}

variable "gateway_ami_id" {
  type        = string
  default     = ""
  description = "Set after packer build completes. Empty = stock Ubuntu fallback."
}

variable "admin_role_name_pattern" {
  type        = string
  description = "IAM Identity Center admin role name pattern for KMS admin access. Adjust if not using IC."
  default     = "AWSReservedSSO_AdministratorAccess_*"
}

variable "github_org_repo" {
  type        = string
  description = "GitHub org/repo for OIDC trust (Packer CI / bundle publish). Format: 'org/repo'."
  default     = "technibears/Agent-Cody"
}

variable "enable_dashboard" {
  type        = bool
  description = "Gate for dashboard control-plane resources (Cognito, CloudFront, DDB pairing, dashboard EC2). Default false while dashboard.tf lives as dashboard.tf.disabled — flip to true only after the missing CloudFront + EC2 resources are completed and the file is renamed back."
  default     = false
}

variable "openclaw_version" {
  type        = string
  description = "Pinned OpenClaw npm version. Update via CVE-bump PR."
  default     = "2026.4.15"
}
