# Run with:  terraform init -backend=false && terraform test
# A mock AWS provider is used, so no AWS account or credentials are needed.
# "apply" here only applies to the mock: nothing is created in AWS.

mock_provider "aws" {
  mock_resource "aws_iam_openid_connect_provider" {
    defaults = {
      arn = "arn:aws:iam::111111111111:oidc-provider/token.actions.githubusercontent.com"
    }
  }
}

variables {
  name_prefix      = "yefter"
  github_subjects  = ["repo:yefterpatino@1234567/demo-app@7654321:environment:prod"]
  target_role_arns = ["arn:aws:iam::222222222222:role/yefter-cicd-deploy"]
}

run "trust_policy_only_allows_the_listed_github_subject" {
  command = apply

  assert {
    condition     = jsondecode(output.trust_policy_json).Statement[0].Action == "sts:AssumeRoleWithWebIdentity"
    error_message = "The pipeline role must be assumed with web identity (OIDC)."
  }

  assert {
    condition     = jsondecode(output.trust_policy_json).Statement[0].Principal.Federated == "arn:aws:iam::111111111111:oidc-provider/token.actions.githubusercontent.com"
    error_message = "The trust policy must point at the GitHub OIDC provider."
  }

  assert {
    condition     = tolist(jsondecode(output.trust_policy_json).Statement[0].Condition.StringEquals["token.actions.githubusercontent.com:sub"]) == var.github_subjects
    error_message = "Only the listed subjects may be trusted."
  }

  assert {
    condition     = jsondecode(output.trust_policy_json).Statement[0].Condition.StringEquals["token.actions.githubusercontent.com:aud"] == "sts.amazonaws.com"
    error_message = "The audience must be sts.amazonaws.com."
  }

  assert {
    condition     = aws_iam_role.this.name == "yefter-cicd-pipeline"
    error_message = "The role name must use the name prefix."
  }
}

run "pipeline_can_only_assume_the_target_roles" {
  command = apply

  assert {
    condition     = length(jsondecode(output.permissions_policy_json).Statement) == 1
    error_message = "The pipeline role must have exactly one statement."
  }

  assert {
    condition     = jsondecode(output.permissions_policy_json).Statement[0].Action == "sts:AssumeRole"
    error_message = "The only allowed action is sts:AssumeRole."
  }

  assert {
    condition     = tolist(jsondecode(output.permissions_policy_json).Statement[0].Resource) == var.target_role_arns
    error_message = "Only the listed target roles may be assumed."
  }
}

run "uses_an_existing_oidc_provider" {
  command = apply

  variables {
    create_github_oidc_provider       = false
    existing_github_oidc_provider_arn = "arn:aws:iam::111111111111:oidc-provider/token.actions.githubusercontent.com"
  }

  assert {
    condition     = length(aws_iam_openid_connect_provider.github) == 0
    error_message = "No provider should be created when one already exists."
  }

  assert {
    condition     = output.oidc_provider_arn == var.existing_github_oidc_provider_arn
    error_message = "The existing provider must be used."
  }
}

# ----------------------------------------------------------- things that must be refused

run "rejects_wildcard_subject" {
  command = plan

  variables {
    github_subjects = ["repo:yefterpatino/*"]
  }

  expect_failures = [var.github_subjects]
}

run "rejects_wildcard_target_role" {
  command = plan

  variables {
    target_role_arns = ["arn:aws:iam::222222222222:role/*"]
  }

  expect_failures = [var.target_role_arns]
}

run "requires_existing_provider_arn_when_not_creating" {
  command = plan

  variables {
    create_github_oidc_provider = false
  }

  expect_failures = [aws_iam_role.this]
}
