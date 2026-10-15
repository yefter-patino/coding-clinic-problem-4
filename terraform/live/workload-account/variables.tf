variable "aws_region" {
  description = "Region for the AWS provider. IAM is global, but the provider still needs one."
  type        = string
}

variable "aws_profile" {
  description = "AWS CLI profile for this WORKLOAD account. Leave empty in CI."
  type        = string
  default     = ""
}

variable "name_prefix" {
  description = "Prefix for every name. Must match the tooling stack."
  type        = string
  default     = "yefter"
}

variable "role_name" {
  description = "Short name of the target role. Must match role_name in the tooling stack's targets list."
  type        = string
  default     = "cicd-deploy"
}

variable "pipeline_role_arn" {
  description = "The pipeline_role_arn output of the tooling stack."
  type        = string
}

variable "external_id" {
  description = "Do NOT put this in a file. Pass it with: export TF_VAR_external_id=..."
  type        = string
  sensitive   = true
}

variable "policy_statements" {
  description = "What the pipeline may do in this account. See modules/target-role/variables.tf for the rules."
  type = list(object({
    sid                     = string
    actions                 = list(string)
    resources               = list(string)
    allow_wildcard_resource = optional(bool, false)
    conditions              = optional(map(map(list(string))), {})
  }))
}

variable "permissions_boundary_arn" {
  description = "Optional permissions boundary ARN."
  type        = string
  default     = null
}

variable "tags" {
  description = "Tags added to every resource."
  type        = map(string)
  default     = {}
}
