# Step 1 of 2: run this in the TOOLING (CI/CD) account first.
# It creates the pipeline role. The target roles do not need to exist yet.

locals {
  # Build the exact ARN of each target role from its account id and name.
  target_role_arns = [
    for t in var.targets :
    "arn:${var.partition}:iam::${t.account_id}:role${t.role_path}${var.name_prefix}-${t.role_name}"
  ]
}

module "pipeline_role" {
  source = "../../modules/pipeline-role"

  name_prefix                       = var.name_prefix
  create_github_oidc_provider       = var.create_github_oidc_provider
  existing_github_oidc_provider_arn = var.existing_github_oidc_provider_arn
  github_subjects                   = var.github_subjects
  target_role_arns                  = local.target_role_arns
  tags                              = var.tags
}
