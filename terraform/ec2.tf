data "aws_ami" "ubuntu" {
  most_recent = true

  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd-gp3/ubuntu-noble-24.04-amd64-server-*"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }

  filter {
    name   = "root-device-type"
    values = ["ebs"]
  }

  owners = ["099720109477"] # Canonical
}

# ---------------- Gateway VM ----------------
resource "aws_instance" "gw" {
  ami                    = var.gateway_ami_id != "" ? var.gateway_ami_id : data.aws_ami.ubuntu.id
  instance_type          = var.gw_instance_type
  subnet_id              = aws_subnet.private[0].id
  vpc_security_group_ids = [aws_security_group.gw.id]
  iam_instance_profile   = aws_iam_instance_profile.gw.name

  metadata_options {
    http_tokens                 = "required"
    http_endpoint               = "enabled"
    http_put_response_hop_limit = 2
    instance_metadata_tags      = "disabled"
  }

  root_block_device {
    # 100 GB leaves ~85 GB free after current workload (12 GB used) for
    # NVIDIA drivers (~500 MB), CUDA runtime (~3 GB), Gemma 12B Q4 (~7 GB),
    # an extra whisper large-v3 GPU build (~3 GB), plus growth headroom.
    volume_size = 100
    volume_type = "gp3"
    encrypted   = true
    kms_key_id  = aws_kms_key.cmk.arn
  }

  tags = merge(local.tags_gw, { Name = "${local.name}-gw" })

  lifecycle {
    ignore_changes = [ami] # AMI bumps via Packer + var, not plan drift
  }
}

# ---------------- Memory VM (Neo4j) ----------------
resource "aws_instance" "mem" {
  ami                    = data.aws_ami.ubuntu.id
  instance_type          = var.mem_instance_type
  subnet_id              = aws_subnet.private[1].id
  vpc_security_group_ids = [aws_security_group.mem.id]
  iam_instance_profile   = aws_iam_instance_profile.mem.name

  metadata_options {
    http_tokens                 = "required"
    http_endpoint               = "enabled"
    http_put_response_hop_limit = 1
    instance_metadata_tags      = "disabled"
  }

  root_block_device {
    volume_size = 30
    volume_type = "gp3"
    encrypted   = true
    kms_key_id  = aws_kms_key.cmk.arn
  }

  user_data_replace_on_change = false
  user_data                   = file("${path.module}/../packer/bootstrap-mem.sh")

  tags = merge(local.tags_mem, { Name = "${local.name}-mem" })

  lifecycle {
    ignore_changes = [user_data] # bootstrap self-wipes after run
  }
}

output "gw_instance_id" { value = aws_instance.gw.id }
output "gw_private_ip" { value = aws_instance.gw.private_ip }
output "mem_instance_id" { value = aws_instance.mem.id }
output "mem_private_ip" { value = aws_instance.mem.private_ip }
