# ---------------------------------------------------------------------------
# Target role: lives in the WORKLOAD account (where things get deployed).
# The CI/CD pipeline role may assume it, but only when it also sends the External ID.
# ---------------------------------------------------------------------------

variable "name_prefix" {
  description = "Prefix for every name this module creates."
  type        = string
  default     = "yefter"

  validation {
    condition     = can(regex("^[a-zA-Z0-9-]{1,20}$", var.name_prefix))
    error_message = "name_prefix: use 1-20 letters, digits or dashes."
  }
}

variable "role_name" {
  description = "Short role name. The full name becomes <name_prefix>-<role_name>."
  type        = string
  default     = "cicd-deploy"

  validation {
    condition     = can(regex("^[a-zA-Z0-9+=,.@_-]{1,40}$", var.role_name))
    error_message = "role_name: use 1-40 letters, digits or + = , . @ _ -"
  }
}

variable "role_path" {
  description = "IAM path for the role. Must start and end with a slash."
  type        = string
  default     = "/"

  validation {
    condition     = can(regex("^/([a-zA-Z0-9+=,.@_-]+/)*$", var.role_path))
    error_message = "role_path must start and end with / (for example / or /cicd/)."
  }
}

variable "pipeline_role_arns" {
  description = "The CI/CD pipeline role(s) allowed to assume this role. Exact role ARNs only."
  type        = list(string)

  validation {
    condition     = length(var.pipeline_role_arns) > 0
    error_message = "Give at least one pipeline role ARN."
  }

  validation {
    condition = alltrue([
      for arn in var.pipeline_role_arns : can(regex("^arn:aws[a-z-]*:iam::[0-9]{12}:role/[a-zA-Z0-9+=,.@_/-]+$", arn))
    ])
    error_message = "Each entry must be an exact IAM role ARN (no wildcards, no account root)."
  }
}

variable "external_id" {
  description = "Shared value the pipeline must send when it assumes this role. Generate it with: python -m xacct new-external-id"
  type        = string
  sensitive   = true

  validation {
    # AWS allows 2-1224 chars of [\w+=,.@:/-]. We ask for at least 32 so it can't be guessed.
    condition     = can(regex("^[a-zA-Z0-9_+=,.@:/-]{32,1224}$", var.external_id))
    error_message = "external_id must be 32-1224 characters of letters, digits or _ + = , . @ : / -"
  }
}

variable "max_session_duration" {
  description = "Longest session allowed, in seconds. A pipeline that chains roles is capped at 3600 by AWS anyway."
  type        = number
  default     = 3600

  validation {
    condition     = var.max_session_duration >= 3600 && var.max_session_duration <= 43200
    error_message = "max_session_duration must be between 3600 and 43200 seconds."
  }
}

variable "policy_statements" {
  description = <<-EOT
    What the pipeline may do in this account (least privilege). Each item becomes one Allow statement.
      sid                     = short name, letters and digits only
      actions                 = exact actions like "s3:PutObject" (no "*" and no "service:*")
      resources               = exact ARNs. "*" is refused unless allow_wildcard_resource = true
      allow_wildcard_resource = set true only for actions that do not support resource ARNs
      conditions              = optional IAM conditions, same shape as in a policy:
                                { StringEquals = { "aws:RequestedRegion" = ["us-east-1"] } }
  EOT
  type = list(object({
    sid                     = string
    actions                 = list(string)
    resources               = list(string)
    allow_wildcard_resource = optional(bool, false)
    conditions              = optional(map(map(list(string))), {})
  }))

  validation {
    condition     = length(var.policy_statements) > 0
    error_message = "Give at least one policy statement."
  }

  validation {
    condition     = alltrue([for s in var.policy_statements : can(regex("^[A-Za-z0-9]+$", s.sid))])
    error_message = "Each sid must contain only letters and digits."
  }

  validation {
    condition     = length(distinct([for s in var.policy_statements : s.sid])) == length(var.policy_statements)
    error_message = "Each sid must be unique."
  }

  validation {
    condition = alltrue(flatten([
      for s in var.policy_statements : [
        for a in s.actions : can(regex("^[a-z0-9-]+:[A-Za-z0-9]+$", a))
      ]
    ]))
    error_message = "Actions must be exact, like s3:PutObject. Wildcards (\"*\", \"s3:*\", \"s3:Get*\") are not allowed: they quietly grant more than you think."
  }

  validation {
    condition = alltrue([
      for s in var.policy_statements : s.allow_wildcard_resource || !contains(s.resources, "*")
    ])
    error_message = "Resource \"*\" is only allowed when allow_wildcard_resource = true for that statement."
  }
}

variable "guardrail_deny_actions" {
  description = "Actions that are always denied, even if an Allow statement or another policy grants them. Stops privilege escalation."
  type        = list(string)
  default = [
    "iam:AttachRolePolicy",
    "iam:CreateAccessKey",
    "iam:CreateLoginProfile",
    "iam:CreatePolicyVersion",
    "iam:CreateRole",
    "iam:CreateUser",
    "iam:DeleteRolePermissionsBoundary",
    "iam:PutRolePermissionsBoundary",
    "iam:PutRolePolicy",
    "iam:SetDefaultPolicyVersion",
    "iam:UpdateAssumeRolePolicy",
    "iam:UpdateLoginProfile",
    "organizations:LeaveOrganization",
    "sts:AssumeRole",
  ]
}

variable "permissions_boundary_arn" {
  description = "Optional permissions boundary (an extra upper limit). Leave null to skip."
  type        = string
  default     = null
}

variable "tags" {
  description = "Extra tags for the role."
  type        = map(string)
  default     = {}
}
