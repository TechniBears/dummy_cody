provider "aws" {
  region = var.region

  default_tags {
    tags = {
      Project     = "agent-cody"
      ManagedBy   = "terraform"
      Environment = "prod"
    }
  }
}
