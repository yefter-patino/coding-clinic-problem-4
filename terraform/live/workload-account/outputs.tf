output "target_role_arn" {
  description = "Put this in the GitHub variable TARGET_ROLE_ARN."
  value       = module.deploy_role.role_arn
}

output "permissions_policy_json" {
  description = "What the pipeline is allowed to do here. Review it."
  value       = module.deploy_role.permissions_policy_json
}
