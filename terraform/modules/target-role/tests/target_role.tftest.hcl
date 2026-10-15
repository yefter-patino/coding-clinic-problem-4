# Run with:  terraform init -backend=false && terraform test
# A mock AWS provider is used, so no AWS account or credentials are needed.

mock_provider "aws" {}

variables {
  name_prefix        = "yefter"
  pipeline_role_arns = ["arn:aws:iam::111111111111:role/yefter-cicd-pipeline"]
  external_id        = "test-only-external-id-0123456789abcdef"
  policy_statements = [
    {
      sid       = "UploadArtifacts"
      actions   = ["s3:PutObject", "s3:ListBucket"]
      resources = ["arn:aws:s3:::yefter-test-artifacts", "arn:aws:s3:::yefter-test-artifacts/*"]
    }
  ]
}

run "trust_policy_requires_the_external_id" {
  command = plan

  assert {
    condition     = jsondecode(aws_iam_role.this.assume_role_policy).Statement[0].Condition.StringEquals["sts:ExternalId"] == var.external_id
    error_message = "The trust policy must require the External ID."
  }

  assert {
    condition     = tolist(jsondecode(aws_iam_role.this.assume_role_policy).Statement[0].Principal.AWS) == var.pipeline_role_arns
    error_message = "Only the pipeline role may be trusted."
  }

  assert {
    condition     = aws_iam_role.this.name == "yefter-cicd-deploy"
    error_message = "The role name must use the name prefix."
  }

  assert {
    condition     = aws_iam_role.this.max_session_duration == 3600
    error_message = "Default session length should be one hour."
  }
}

run "permissions_have_allow_and_guardrail_deny" {
  command = plan

  assert {
    condition     = jsondecode(output.permissions_policy_json).Statement[0].Action == ["s3:PutObject", "s3:ListBucket"]
    error_message = "The Allow statement must contain exactly the listed actions."
  }

  assert {
    condition     = jsondecode(output.permissions_policy_json).Statement[1].Effect == "Deny"
    error_message = "The guardrail Deny statement must be present."
  }

  assert {
    condition     = !can(jsondecode(output.permissions_policy_json).Statement[0].Condition)
    error_message = "No Condition block should be added when none was given."
  }
}

run "conditions_are_copied_into_the_statement" {
  command = plan

  variables {
    policy_statements = [
      {
        sid        = "UploadArtifacts"
        actions    = ["s3:PutObject"]
        resources  = ["arn:aws:s3:::yefter-test-artifacts/*"]
        conditions = { StringEquals = { "aws:RequestedRegion" = ["us-east-1"] } }
      }
    ]
  }

  assert {
    condition     = jsondecode(output.permissions_policy_json).Statement[0].Condition.StringEquals["aws:RequestedRegion"] == ["us-east-1"]
    error_message = "The condition must be copied as given."
  }
}

run "wildcard_resource_allowed_only_when_asked" {
  command = plan

  variables {
    policy_statements = [
      {
        sid                     = "EcrLogin"
        actions                 = ["ecr:GetAuthorizationToken"]
        resources               = ["*"]
        allow_wildcard_resource = true
      }
    ]
  }

  assert {
    condition     = jsondecode(output.permissions_policy_json).Statement[0].Resource == ["*"]
    error_message = "A wildcard resource should be accepted when allow_wildcard_resource = true."
  }
}

# ----------------------------------------------------------- things that must be refused

run "rejects_service_wildcard_action" {
  command = plan

  variables {
    policy_statements = [{ sid = "TooBroad", actions = ["s3:*"], resources = ["arn:aws:s3:::yefter-test-artifacts"] }]
  }

  expect_failures = [var.policy_statements]
}

run "rejects_prefix_wildcard_action" {
  command = plan

  variables {
    policy_statements = [{ sid = "TooBroad", actions = ["secretsmanager:Get*"], resources = ["arn:aws:secretsmanager:us-east-1:222222222222:secret:x"] }]
  }

  expect_failures = [var.policy_statements]
}

run "rejects_wildcard_resource_without_flag" {
  command = plan

  variables {
    policy_statements = [{ sid = "TooBroad", actions = ["s3:PutObject"], resources = ["*"] }]
  }

  expect_failures = [var.policy_statements]
}

run "rejects_short_external_id" {
  command = plan

  variables {
    external_id = "abc123"
  }

  expect_failures = [var.external_id]
}

run "rejects_wildcard_principal" {
  command = plan

  variables {
    pipeline_role_arns = ["*"]
  }

  expect_failures = [var.pipeline_role_arns]
}

run "rejects_account_root_principal" {
  command = plan

  variables {
    pipeline_role_arns = ["arn:aws:iam::111111111111:root"]
  }

  expect_failures = [var.pipeline_role_arns]
}

run "rejects_action_that_the_guardrail_denies" {
  command = plan

  variables {
    policy_statements = [{ sid = "Escalate", actions = ["iam:CreateUser"], resources = ["arn:aws:iam::222222222222:user/x"] }]
  }

  expect_failures = [aws_iam_role_policy.permissions]
}
