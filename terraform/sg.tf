resource "aws_security_group" "gw" {
  name_prefix = "${local.name}-gw-"
  vpc_id      = aws_vpc.main.id
  description = "Agent Cody Gateway VM"

  # Phase 0 permissive egress; Phase 4 tightens via proxy + FQDN allow-list
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
    description = "PHASE0 PERMISSIVE - Phase 4 replaces with egress proxy"
  }

  tags = merge(local.tags_gw, { Name = "${local.name}-sg-gw" })

  lifecycle { create_before_destroy = true }
}

resource "aws_security_group" "mem" {
  name_prefix = "${local.name}-mem-"
  vpc_id      = aws_vpc.main.id
  description = "Agent Cody Memory VM (Neo4j)"

  ingress {
    description     = "Neo4j Bolt from gw"
    from_port       = 7687
    to_port         = 7687
    protocol        = "tcp"
    security_groups = [aws_security_group.gw.id]
  }

  ingress {
    description     = "Neo4j HTTP API from gw"
    from_port       = 7474
    to_port         = 7474
    protocol        = "tcp"
    security_groups = [aws_security_group.gw.id]
  }

  egress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
    description = "HTTPS out for apt-get, SSM, Secrets Manager"
  }

  egress {
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
    description = "HTTP for apt-get"
  }

  tags = merge(local.tags_mem, { Name = "${local.name}-sg-mem" })

  lifecycle { create_before_destroy = true }
}

resource "aws_security_group" "lambda" {
  name_prefix = "${local.name}-lambda-"
  vpc_id      = aws_vpc.main.id
  description = "Agent Cody Lambda functions (egress 443 only)"

  egress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
    description = "HTTPS only - tighter per-function SG in Phase 4"
  }

  tags = { Name = "${local.name}-sg-lambda" }

  lifecycle { create_before_destroy = true }
}
