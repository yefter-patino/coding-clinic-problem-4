output "role_arn" {
  description = "ARN of the target role. The pipeline assumes this."
  value       = aws_iam_role.this.arn
}

output "role_name" {
  description = "Full name of the target role."
  value       = aws_iam_role.this.name
}

output "permissions_policy_json" {
  description = "The permissions policy, for review."
  value       = jsonencode(local.permissions_policy)
}
