locals {
  name = var.name_prefix

  azs = ["${var.region}a", "${var.region}b"]

  private_subnet_cidrs = [
    cidrsubnet(var.vpc_cidr, 8, 1), # 10.40.1.0/24
    cidrsubnet(var.vpc_cidr, 8, 2), # 10.40.2.0/24
  ]

  public_subnet_cidr = cidrsubnet(var.vpc_cidr, 8, 100) # 10.40.100.0/24 (NAT only)

  tags_gw   = { Component = "gateway" }
  tags_mem  = { Component = "memory" }
  tags_data = { Component = "data" }
}

data "aws_caller_identity" "current" {}

data "aws_region" "current" {}
