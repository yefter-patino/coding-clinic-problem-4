# Step 2 of 2: run this in EACH workload account, after the tooling stack.
# AWS checks that the trusted pipeline role exists, so the tooling stack must be applied first.

module "deploy_role" {
  source = "../../modules/target-role"

  name_prefix              = var.name_prefix
  role_name                = var.role_name
  pipeline_role_arns       = [var.pipeline_role_arn]
  external_id              = var.external_id
  policy_statements        = var.policy_statements
  permissions_boundary_arn = var.permissions_boundary_arn
  tags                     = var.tags
}
