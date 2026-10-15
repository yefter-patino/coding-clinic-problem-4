output "role_arn" {
  description = "ARN of the pipeline role. Put it in the GitHub variable PIPELINE_ROLE_ARN and in each target role's trust policy."
  value       = aws_iam_role.this.arn
}

output "role_name" {
  description = "Full name of the pipeline role."
  value       = aws_iam_role.this.name
}

output "oidc_provider_arn" {
  description = "ARN of the GitHub OIDC provider used by the role."
  value       = local.oidc_provider_arn
}

output "trust_policy_json" {
  description = "The trust policy, for review."
  value       = jsonencode(local.trust_policy)
}

output "permissions_policy_json" {
  description = "The permissions policy, for review."
  value       = jsonencode(local.permissions_policy)
}
