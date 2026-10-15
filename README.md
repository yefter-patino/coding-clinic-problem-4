# Problem #4

**Implement a reusable Terraform + Python hybrid that creates a cross-account IAM role assuming
pattern with external ID and least-privilege policies for a CI/CD pipeline.**

## What this builds

A pipeline (GitHub Actions) that lives in one AWS account, the **tooling** account, deploys into other
AWS accounts, the **workload** accounts, without any stored AWS keys and with the smallest set of
permissions possible.

- **Terraform** creates the roles: a reusable module for each side, plus a ready-to-use "live" stack
  for each account.
- **Python** (`xacct`) is used at run time: it creates the External ID, assumes the target role inside
  the pipeline, and **proves** the setup is locked down (access without the External ID is denied, and
  the policy allows only what you expect).

## Architecture

```
 GitHub Actions job (repo + "prod" environment)
        │  1. OIDC token  (no AWS keys stored in GitHub)
        ▼
┌───────────────────── TOOLING account ─────────────────────┐
│  IAM OIDC provider: token.actions.githubusercontent.com    │
│  Role: yefter-cicd-pipeline                                │
│    trust : only this exact GitHub "sub" (repo + env)       │
│    allow : sts:AssumeRole on the listed target roles ONLY  │
└──────────────────────────┬─────────────────────────────────┘
                           │  2. sts:AssumeRole + ExternalId   (python -m xacct assume)
                           ▼
┌───────────────────── WORKLOAD account ────────────────────┐
│  Role: yefter-cicd-deploy                                  │
│    trust : only yefter-cicd-pipeline AND the External ID   │
│    allow : exact actions on exact resources (your list)    │
│    deny  : privilege-escalation guardrail (always wins)    │
└──────────────────────────┬─────────────────────────────────┘
                           │  3. short-lived credentials (15-60 min)
                           ▼
                deploy steps (S3 upload, ECR push, ...)
```

Two locks must both open before anything can be deployed:

| Lock | Where | Stops |
|---|---|---|
| GitHub OIDC subject | pipeline role trust policy | any other repo, branch or environment |
| External ID | target role trust policy | anyone who can assume the pipeline role but was not given the External ID (the "confused deputy" problem) |

## Repository layout

```
Problem #4/
├── terraform/
│   ├── modules/
│   │   ├── pipeline-role/          reusable: OIDC provider + pipeline role (tooling account)
│   │   │   └── tests/              terraform test, mock AWS provider
│   │   └── target-role/            reusable: External-ID role + least-privilege policy (workload account)
│   │       └── tests/
│   └── live/
│       ├── tooling-account/        step 1: apply in the tooling account
│       └── workload-account/       step 2: apply in each workload account
├── xacct/                          Python tool
│   ├── external_id.py              create and check External IDs
│   ├── assume.py                   assume the target role, output the credentials
│   ├── verify.py                   trust checks + IAM policy simulator checks
│   └── cli.py                      the command line
├── tests/                          pytest (scripted AWS answers, no account needed)
├── config/expectations.example.json   what the target role should and should not be able to do
├── examples/                       sample policies and sample verify output (synthetic)
└── .github/workflows/
    ├── ci.yml                      lint, tests, terraform fmt/validate/test, checkov
    └── deploy-example.yml          how a real pipeline uses the roles
```

## Prerequisites

| Tool | Version | Check |
|---|---|---|
| Terraform | 1.11 or newer (CI uses 1.16.0) | `terraform -version` |
| AWS provider | 6.x (downloaded by `terraform init`) | |
| Python | 3.10 or newer | `python3 --version` |
| AWS CLI | v2 | `aws --version` |
| GitHub CLI (optional) | any | `gh --version` |

You also need:
- Two AWS CLI profiles with admin rights to create IAM roles: one for the tooling account and one for
  the workload account (the examples call them `tooling` and `workload`). One account can play both
  parts while you learn.
- A GitHub repository for the pipeline.

Cost: IAM roles, policies and OIDC providers are free.

## Quick start

### 1. Install the Python tool

```bash
cd "Problem #4"
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Create the External ID

```bash
export XACCT_EXTERNAL_ID="$(python -m xacct new-external-id)"
echo "$XACCT_EXTERNAL_ID"     # save it in your password manager
```

It is never written to a file in this project. Terraform reads it from `TF_VAR_external_id`, xacct
reads it from `XACCT_EXTERNAL_ID`, and GitHub keeps it as an environment secret.

### 3. Find your GitHub subject

The pipeline role trusts one exact OIDC `sub` value. Since 15 July 2026, **new** GitHub repositories
include the owner and repository IDs in it:

```
repo:OWNER@OWNER_ID/REPO@REPO_ID:environment:prod      (new repos, or repos that opted in)
repo:OWNER/REPO:environment:prod                       (older repos that did not opt in)
```

Build the new-format value with the GitHub CLI:

```bash
gh api repos/OWNER/REPO --jq '"repo:\(.owner.login)@\(.owner.id)/\(.name)@\(.id):environment:prod"'
```

Not sure which format your repo uses? See "Troubleshooting" for a workflow step that prints it.

### 4. Apply the tooling stack (pipeline role)

```bash
cd terraform/live/tooling-account
cp terraform.tfvars.example terraform.tfvars      # edit: profile, github_subjects, targets
terraform init
terraform plan
terraform apply
terraform output pipeline_role_arn                # you need this in step 5 and 6
```

### 5. Apply the workload stack (target role), in each workload account

```bash
cd ../workload-account
cp terraform.tfvars.example terraform.tfvars      # edit: profile, pipeline_role_arn, policy_statements
export TF_VAR_external_id="$XACCT_EXTERNAL_ID"
terraform init
terraform plan
terraform apply
terraform output target_role_arn
```

The tooling stack must be applied first. AWS refuses a trust policy that names a role that does not
exist yet.

### 6. Configure GitHub

Repository **Settings → Environments → New environment → `prod`**:

| Type | Name | Value |
|---|---|---|
| Variable | `AWS_REGION` | for example `us-east-1` |
| Variable | `PIPELINE_ROLE_ARN` | output of step 4 |
| Variable | `TARGET_ROLE_ARN` | output of step 5 |
| Variable | `ARTIFACT_BUCKET` | your artifact bucket (used by the example deploy) |
| Secret | `XACCT_EXTERNAL_ID` | the value from step 2 |

Add **Required reviewers** to the environment, so a person approves every deployment.
Then run the **deploy-example** workflow from the Actions tab.

### 7. Prove it is locked down

**Trust checks** need the pipeline role's credentials, because only that role is trusted. They run
inside the pipeline: `deploy-example.yml` has a step that runs them before every deploy and stops the
job if any check fails.

```bash
python -m xacct verify --role-arn "$TARGET_ROLE_ARN"
```

**Least-privilege checks** use the IAM policy simulator. Run them from your laptop with an
admin/auditor profile in the workload account:

```bash
cp config/expectations.example.json config/expectations.json    # edit the REPLACE values
python -m xacct verify --role-arn "$TARGET_ROLE_ARN" --policy-only \
  --expectations config/expectations.json --simulate-profile workload
```

Both kinds can run in one command (leave out `--policy-only`) when the same machine has the pipeline
role credentials and a workload admin profile, but usually they run in the two places above.

Sample output is in `examples/sample-verify-output.txt`. The exit code is 0 when every check passes and
2 when any check fails, so it can run as a pipeline gate.

## xacct commands

| Command | What it does |
|---|---|
| `python -m xacct new-external-id [--length 48]` | Prints a new random External ID (32-1224 characters). |
| `python -m xacct assume --role-arn ARN --format env` | Prints `export ...` lines. Use `eval "$(python -m xacct assume ...)"` on a laptop. |
| `python -m xacct assume --role-arn ARN --format github` | In GitHub Actions: masks the values in the logs and passes them to the next steps. |
| `python -m xacct assume --role-arn ARN --format credential-process` | JSON for an AWS CLI profile, see below. |
| `python -m xacct verify --role-arn ARN [--expectations FILE --simulate-profile P] [--policy-only]` | Runs the checks described in step 7. |

Options for `assume` and `verify`:

| Option | Environment variable | Default |
|---|---|---|
| `--role-arn` | `XACCT_ROLE_ARN` | required |
| `--external-id-env` | (names the variable to read) | `XACCT_EXTERNAL_ID` |
| `--profile` | `XACCT_PROFILE` | normal AWS credentials |
| `--region` | `AWS_REGION` | normal AWS default |
| `--name-prefix` | `XACCT_NAME_PREFIX` | `yefter` |
| `--duration` (assume only) | | `900` seconds, maximum `3600` |
| `--simulate-profile` (verify only) | `XACCT_SIMULATE_PROFILE` | |

Using the target role from the AWS CLI on your laptop (`~/.aws/config`):

```ini
[profile yefter-deploy]
credential_process = python -m xacct assume --role-arn arn:aws:iam::WORKLOAD_ID:role/yefter-cicd-deploy --profile tooling --format credential-process
```

## Terraform inputs (most used)

**`modules/pipeline-role`**

| Variable | Default | Meaning |
|---|---|---|
| `name_prefix` | `yefter` | Prefix for all names |
| `role_name` | `cicd-pipeline` | Role becomes `yefter-cicd-pipeline` |
| `create_github_oidc_provider` | `true` | `false` if the account already has one (only one per URL is allowed) |
| `existing_github_oidc_provider_arn` | `""` | Needed when the above is `false` |
| `github_subjects` | required | Exact `sub` values. Wildcards are refused |
| `target_role_arns` | required | Exact target role ARNs. Wildcards are refused |

**`modules/target-role`**

| Variable | Default | Meaning |
|---|---|---|
| `name_prefix` | `yefter` | Prefix for all names |
| `role_name` | `cicd-deploy` | Role becomes `yefter-cicd-deploy` |
| `pipeline_role_arns` | required | Exact role ARNs. `*` and account roots are refused |
| `external_id` | required, sensitive | 32-1224 characters |
| `policy_statements` | required | The allowed actions, see below |
| `guardrail_deny_actions` | IAM/STS escalation list | Always denied, even if allowed elsewhere |
| `permissions_boundary_arn` | `null` | Optional extra upper limit |
| `max_session_duration` | `3600` | 3600-43200 |

`policy_statements` rules, enforced by Terraform validation (the plan fails if you break one):
- Actions must be exact (`s3:PutObject`). `*`, `s3:*` and `s3:Get*` are refused. Prefix wildcards
  quietly include actions you did not mean, for example `secretsmanager:Get*` includes `GetSecretValue`.
- Resource `*` is refused unless that statement sets `allow_wildcard_resource = true`, which is only
  for actions that do not support resource ARNs (for example `ecr:GetAuthorizationToken`).
- An allowed action may not also be in the guardrail Deny list.

## Security considerations

- **No long-lived keys.** GitHub uses OIDC, and every credential is temporary (15-60 minutes).
- **The External ID is not a password.** Anyone who can read the role in IAM can see it. It protects
  against the confused-deputy problem: a caller that can assume the pipeline role still cannot use the
  target role without the value. Treat it as confidential anyway: environment secret, never a file,
  never a command-line argument (xacct only reads it from an environment variable).
- **It ends up in Terraform state**, because it is part of the trust policy. Use an encrypted S3
  backend with restricted access (`backend.tf.example`) for anything beyond learning.
- **Least privilege on both sides.** The pipeline role can do exactly one thing (assume the listed
  roles). The target role can do only the listed actions on the listed resources.
- **Guardrail Deny.** Even if someone later attaches a broad policy to the target role, the explicit
  Deny still blocks creating users, keys, roles, editing policies and chaining to other roles.
- **Pin the GitHub environment** in the subject (`:environment:prod`) and add required reviewers to it.
  Then a branch push alone cannot deploy.
- **Audit trail.** The role session name is `yefter-cicd-<run id>-<attempt>`, so CloudTrail in the
  workload account shows exactly which pipeline run did what.
- **`iam:PassRole`** is not in the default guardrail because ECS and Lambda deployments need it. If you
  allow it, always scope it to exact role ARNs and add an `iam:PassedToService` condition.

## Idempotency

- `terraform apply` can be run again at any time. With no changes it reports "No changes".
- Changing a policy list updates the policy in place. The roles are not re-created.
- `xacct assume` and `xacct verify` change nothing in AWS. Each run just gets new temporary credentials.
- `xacct new-external-id` makes a new value every time. Run it once. Rotating the value means:
  update `TF_VAR_external_id`, apply the workload stack, then update the GitHub secret.

## Testing and CI

```bash
pip install -r requirements-dev.txt
ruff check . && ruff format --check .
pytest                                            # 47 tests, no AWS account needed

cd terraform/modules/target-role && terraform init -backend=false && terraform test
cd ../pipeline-role               && terraform init -backend=false && terraform test
checkov -d terraform --framework terraform --quiet --skip-download
```

- The Python tests script the AWS answers with botocore's `Stubber`, including the denial cases, so
  they check the real request parameters (for example that the External ID is actually sent).
- The Terraform tests use a mock AWS provider. They check the trust and permissions policies that get
  built, and that bad input (wildcards, short External IDs, account-root principals) is refused.
- `ci.yml` runs all of this on every push and pull request.

## Limitations

- The Terraform code was checked with an HCL parser and checkov (22 checks passed, 0 failed), but
  Terraform itself could not be run where this was written. CI or your first `terraform init` and
  `terraform test` is the first real run. Nothing has been applied to a real AWS account.
- The policy simulator checks identity policies and the permissions boundary. It does not include
  resource policies (for example S3 bucket policies) or Organizations SCPs.
- Role chaining (OIDC role → target role) is limited by AWS to a one-hour session.
- If you use `aws-actions/configure-aws-credentials` with `role-chaining: true` instead of xacct for the
  second hop, also set `role-skip-session-tagging: true`, because the target trust policy does not
  allow `sts:TagSession`.

## Troubleshooting

| Message | Cause | Fix |
|---|---|---|
| `Not authorized to perform sts:AssumeRoleWithWebIdentity` | The GitHub `sub` does not match `github_subjects` | Print your real subject with the step below and update the tfvars |
| `MalformedPolicyDocument: Invalid principal` on the workload apply | The pipeline role does not exist yet | Apply the tooling stack first |
| `EntityAlreadyExists` on the OIDC provider | The account already has the GitHub provider | `create_github_oidc_provider = false` and set `existing_github_oidc_provider_arn` |
| `AccessDenied` from `xacct assume` | Wrong External ID, or the target role does not trust this caller | Compare `XACCT_EXTERNAL_ID` with `TF_VAR_external_id`. Run `aws sts get-caller-identity` |
| `environment variable XACCT_EXTERNAL_ID is empty` | Secret not set, or not passed to the step | Add `env: XACCT_EXTERNAL_ID: ${{ secrets.XACCT_EXTERNAL_ID }}` to the step |
| `duration must be 900-3600 seconds` | Role chaining is limited to one hour | Use `--duration 3600` or less |

Workflow step that prints your OIDC subject (it prints only the `sub`, never the token):

```yaml
- name: Show my OIDC subject
  run: |
    TOKEN=$(curl -sS -H "Authorization: bearer $ACTIONS_ID_TOKEN_REQUEST_TOKEN" \
      "$ACTIONS_ID_TOKEN_REQUEST_URL&audience=sts.amazonaws.com" | python3 -c "import sys, json; print(json.load(sys.stdin)['value'])")
    python3 -c "import sys, json, base64; p = sys.argv[1].split('.')[1]; p += '=' * (-len(p) % 4); print(json.loads(base64.urlsafe_b64decode(p))['sub'])" "$TOKEN"
```

The job needs `permissions: id-token: write` and the same `environment:` as the deploy job.

## Clean up

```bash
cd terraform/live/workload-account && terraform destroy    # each workload account first
cd ../tooling-account              && terraform destroy
```
