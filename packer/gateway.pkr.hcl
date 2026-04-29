# Agent Cody Gateway AMI — Ubuntu 24.04 + Node 22 + ffmpeg + Docker + Piper + whisper-ctranslate2 + OpenClaw
#
# Builds in the agent-cody private subnet via SSM Session Manager (no public IP during build).
# Requires: terraform apply must have completed first (needs the VPC + packer instance profile).

packer {
  required_plugins {
    amazon = {
      source  = "github.com/hashicorp/amazon"
      version = "~> 1.3"
    }
  }
}

variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "openclaw_version" {
  type        = string
  description = "OpenClaw npm version. Current stable (2026-04-18): 2026.4.15"
  default     = "2026.4.15"
}

source "amazon-ebs" "gateway" {
  region = var.aws_region

  source_ami_filter {
    filters = {
      name                = "ubuntu/images/hvm-ssd-gp3/ubuntu-noble-24.04-amd64-server-*"
      virtualization-type = "hvm"
      root-device-type    = "ebs"
    }
    owners      = ["099720109477"]
    most_recent = true
  }

  instance_type = "g4dn.xlarge"

  # Public-subnet build with public IP (MVP — scrutiny H9 accepted).
  # Phase 4 hardening migrates to private subnet + SSM when session-manager-plugin is
  # installed on the operator's workstation.
  vpc_filter {
    filters = { "tag:Name" = "agent-cody-vpc" }
  }
  subnet_filter {
    filters = { "tag:Name" = "agent-cody-nat-public" }
    random  = false
  }
  associate_public_ip_address = true
  communicator                = "ssh"
  ssh_username                = "ubuntu"
  # Temporary keypair + SG auto-created by Packer; SG locks inbound SSH to Packer's own IP.

  ami_name        = "agent-cody-gw-{{timestamp}}"
  ami_description = "Agent Cody Gateway: Ubuntu 24.04 + Node 22 + ffmpeg + Docker + Piper + whisper-ctranslate2 + Ollama + Gemma4 + OpenClaw ${var.openclaw_version}"

  tags = {
    Project         = "agent-cody"
    OpenClawVersion = var.openclaw_version
    BuildDate       = "{{isotime \"2006-01-02T15:04:05Z\"}}"
  }

  run_tags = {
    Purpose = "packer-build-temp"
    Project = "agent-cody"
  }

  launch_block_device_mappings {
    device_name           = "/dev/sda1"
    volume_size           = 50
    volume_type           = "gp3"
    delete_on_termination = true
    encrypted             = true
  }
}

build {
  sources = ["source.amazon-ebs.gateway"]

  provisioner "shell" {
    script           = "scripts/install-base.sh"
    environment_vars = ["DEBIAN_FRONTEND=noninteractive"]
    execute_command  = "sudo -E -H bash -c '{{ .Vars }} {{ .Path }}'"
  }

  provisioner "shell" {
    script           = "scripts/install-openclaw.sh"
    environment_vars = ["OPENCLAW_VERSION=${var.openclaw_version}"]
    execute_command  = "sudo -E -H bash -c '{{ .Vars }} {{ .Path }}'"
  }

  post-processor "manifest" {
    output     = "manifest.json"
    strip_path = true
    custom_data = {
      openclaw_version = var.openclaw_version
    }
  }
}
