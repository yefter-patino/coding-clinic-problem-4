output "pipeline_role_arn" {
  description = "Use this as pipeline_role_arn in the workload stack, and as the GitHub variable PIPELINE_ROLE_ARN."
  value       = module.pipeline_role.role_arn
}

output "target_role_arns" {
  description = "The target roles the pipeline may assume."
  value       = local.target_role_arns
}
