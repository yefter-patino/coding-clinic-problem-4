locals {
  full_role_name = "${var.name_prefix}-${var.role_name}"

  # Who may assume this role: ONLY the listed pipeline role(s), and ONLY with the External ID.
  trust_policy = {
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "AllowPipelineRoleWithExternalId"
        Effect    = "Allow"
        Principal = { AWS = var.pipeline_role_arns }
        Action    = "sts:AssumeRole"
        Condition = {
          StringEquals = { "sts:ExternalId" = var.external_id }
        }
      }
    ]
  }

  # One Allow statement per item in var.policy_statements.
  allow_statements = [
    for s in var.policy_statements : merge(
      {
        Sid      = s.sid
        Effect   = "Allow"
        Action   = s.actions
        Resource = s.resources
      },
      # Add a Condition block only when the statement has conditions.
      { for key, value in { Condition = s.conditions } : key => value if length(value) > 0 }
    )
  ]

  # An explicit Deny always wins over any Allow, so these actions can never be used.
  deny_statements = length(var.guardrail_deny_actions) == 0 ? [] : [
    {
      Sid      = "GuardrailDenyPrivilegeEscalation"
      Effect   = "Deny"
      Action   = var.guardrail_deny_actions
      Resource = "*"
    }
  ]

  permissions_policy = {
    Version   = "2012-10-17"
    Statement = concat(local.allow_statements, local.deny_statements)
  }

  allowed_actions = toset(flatten([for s in var.policy_statements : s.actions]))
}

resource "aws_iam_role" "this" {
  name                 = local.full_role_name
  path                 = var.role_path
  description          = "Assumed by the CI/CD pipeline (External ID required). Managed by Terraform."
  assume_role_policy   = jsonencode(local.trust_policy)
  max_session_duration = var.max_session_duration
  permissions_boundary = var.permissions_boundary_arn

  tags = merge(var.tags, {
    Name      = local.full_role_name
    ManagedBy = "terraform"
    Purpose   = "cicd-cross-account-target"
  })
}

resource "aws_iam_role_policy" "permissions" {
  name   = "${local.full_role_name}-permissions"
  role   = aws_iam_role.this.id
  policy = jsonencode(local.permissions_policy)

  lifecycle {
    precondition {
      condition     = length(setintersection(local.allowed_actions, toset(var.guardrail_deny_actions))) == 0
      error_message = "An action in policy_statements is also in guardrail_deny_actions, so it would always be denied. Remove it from one of the two lists."
    }
  }
}
