terraform {
  required_version = ">= 1.11.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 6.0, < 7.0"
    }
  }

  # State is kept locally while you learn. For a team, store it in S3 instead:
  # copy backend.tf.example to backend.tf, fill it in, and run terraform init again.
}

provider "aws" {
  region = var.aws_region
  # Empty profile = use the normal credentials (environment variables in CI, default profile on a laptop).
  profile = var.aws_profile != "" ? var.aws_profile : null

  default_tags {
    tags = merge(var.tags, { Project = "${var.name_prefix}-cicd-cross-account" })
  }
}
