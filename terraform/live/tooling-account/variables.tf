variable "aws_region" {
  description = "Region for the AWS provider. IAM is global, but the provider still needs one."
  type        = string
}

variable "aws_profile" {
  description = "AWS CLI profile for the TOOLING (CI/CD) account. Leave empty in CI."
  type        = string
  default     = ""
}

variable "name_prefix" {
  description = "Prefix for every name. Must match the one used in the workload accounts."
  type        = string
  default     = "yefter"
}

variable "partition" {
  description = "AWS partition: aws, aws-us-gov or aws-cn."
  type        = string
  default     = "aws"
}

variable "create_github_oidc_provider" {
  description = "Create the GitHub OIDC provider in this account (false if it already exists)."
  type        = bool
  default     = true
}

variable "existing_github_oidc_provider_arn" {
  description = "ARN of the existing GitHub OIDC provider (only when create_github_oidc_provider = false)."
  type        = string
  default     = ""
}

variable "github_subjects" {
  description = "Exact GitHub OIDC sub values allowed to use the pipeline role. See the README."
  type        = list(string)
}

variable "targets" {
  description = "The workload accounts and the target role in each one that the pipeline may assume."
  type = list(object({
    account_id = string
    role_name  = optional(string, "cicd-deploy")
    role_path  = optional(string, "/")
  }))

  validation {
    condition     = alltrue([for t in var.targets : can(regex("^[0-9]{12}$", t.account_id))])
    error_message = "Each account_id must be 12 digits."
  }
}

variable "tags" {
  description = "Tags added to every resource."
  type        = map(string)
  default     = {}
}
