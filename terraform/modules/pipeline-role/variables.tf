# ---------------------------------------------------------------------------
# Pipeline role: lives in the CI/CD (tooling) account.
# GitHub Actions logs in to it with OIDC (no stored AWS keys). Its ONLY permission
# is to assume the listed target roles in the workload accounts.
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
  default     = "cicd-pipeline"

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

variable "create_github_oidc_provider" {
  description = "Create the GitHub OIDC identity provider. An account can have only one per URL, so set false if it already exists."
  type        = bool
  default     = true
}

variable "existing_github_oidc_provider_arn" {
  description = "ARN of the GitHub OIDC provider that already exists. Only used when create_github_oidc_provider = false."
  type        = string
  default     = ""
}

variable "github_oidc_host" {
  description = "Host that issues the GitHub OIDC tokens. Only change it for GitHub Enterprise Cloud with data residency."
  type        = string
  default     = "token.actions.githubusercontent.com"
}

variable "github_subjects" {
  description = <<-EOT
    Exact GitHub OIDC "sub" values allowed to use this role. No wildcards.
    New repositories (created after 15 July 2026) include immutable IDs, for example:
      repo:yefterpatino@1234567/my-app@7654321:environment:prod
    Older repositories that did not opt in look like:
      repo:yefterpatino/my-app:environment:prod
    See the README for how to find yours.
  EOT
  type        = list(string)

  validation {
    condition     = length(var.github_subjects) > 0
    error_message = "Give at least one GitHub subject."
  }

  validation {
    condition     = alltrue([for s in var.github_subjects : startswith(s, "repo:") && !strcontains(s, "*") && !strcontains(s, "?")])
    error_message = "Each subject must start with repo: and contain no wildcards (* or ?)."
  }
}

variable "target_role_arns" {
  description = "Target roles in the workload accounts that this pipeline may assume. Exact ARNs only."
  type        = list(string)

  validation {
    condition     = length(var.target_role_arns) > 0
    error_message = "Give at least one target role ARN."
  }

  validation {
    condition = alltrue([
      for arn in var.target_role_arns : can(regex("^arn:aws[a-z-]*:iam::[0-9]{12}:role/[a-zA-Z0-9+=,.@_/-]+$", arn))
    ])
    error_message = "Each entry must be an exact IAM role ARN (no wildcards)."
  }
}

variable "max_session_duration" {
  description = "Longest session allowed, in seconds."
  type        = number
  default     = 3600

  validation {
    condition     = var.max_session_duration >= 3600 && var.max_session_duration <= 43200
    error_message = "max_session_duration must be between 3600 and 43200 seconds."
  }
}

variable "tags" {
  description = "Extra tags for everything this module creates."
  type        = map(string)
  default     = {}
}
