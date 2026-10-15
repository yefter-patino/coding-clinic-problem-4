locals {
  full_role_name = "${var.name_prefix}-${var.role_name}"

  # Use the provider we create, or the one that already exists in the account.
  oidc_provider_arn = (
    var.create_github_oidc_provider
    ? aws_iam_openid_connect_provider.github[0].arn
    : var.existing_github_oidc_provider_arn
  )

  # Who may use this role: only GitHub Actions jobs whose token "sub" matches exactly.
  trust_policy = {
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "AllowGitHubActionsOidc"
        Effect    = "Allow"
        Principal = { Federated = local.oidc_provider_arn }
        Action    = "sts:AssumeRoleWithWebIdentity"
        Condition = {
          StringEquals = {
            "${var.github_oidc_host}:aud" = "sts.amazonaws.com"
            "${var.github_oidc_host}:sub" = var.github_subjects
          }
        }
      }
    ]
  }

  # What this role may do: assume the listed target roles. Nothing else.
  permissions_policy = {
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "AssumeOnlyListedTargetRoles"
        Effect   = "Allow"
        Action   = "sts:AssumeRole"
        Resource = var.target_role_arns
      }
    ]
  }

  common_tags = merge(var.tags, { ManagedBy = "terraform" })
}

resource "aws_iam_openid_connect_provider" "github" {
  count = var.create_github_oidc_provider ? 1 : 0

  url            = "https://${var.github_oidc_host}"
  client_id_list = ["sts.amazonaws.com"]

  tags = merge(local.common_tags, { Name = "${var.name_prefix}-github-oidc" })
}

resource "aws_iam_role" "this" {
  name                 = local.full_role_name
  path                 = var.role_path
  description          = "Used by GitHub Actions through OIDC. Can only assume the listed target roles. Managed by Terraform."
  assume_role_policy   = jsonencode(local.trust_policy)
  max_session_duration = var.max_session_duration

  tags = merge(local.common_tags, {
    Name    = local.full_role_name
    Purpose = "cicd-pipeline"
  })

  lifecycle {
    precondition {
      condition     = var.create_github_oidc_provider || can(regex("^arn:aws[a-z-]*:iam::[0-9]{12}:oidc-provider/.+$", var.existing_github_oidc_provider_arn))
      error_message = "Set existing_github_oidc_provider_arn when create_github_oidc_provider = false."
    }
  }
}

resource "aws_iam_role_policy" "assume_targets" {
  name   = "${local.full_role_name}-assume-targets"
  role   = aws_iam_role.this.id
  policy = jsonencode(local.permissions_policy)
}
