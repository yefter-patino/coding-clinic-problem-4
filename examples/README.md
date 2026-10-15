# Examples

**Everything here is synthetic.** The account ids (111111111111 = tooling, 222222222222 = workload),
bucket, repository and GitHub ids are made up.

| File | What it is |
|---|---|
| `pipeline-role-trust-policy.json` | Who may use the pipeline role: one GitHub repo + environment, through OIDC |
| `pipeline-role-permissions-policy.json` | What the pipeline role may do: assume the listed target role, nothing else |
| `target-role-trust-policy.json` | Who may use the target role: the pipeline role, only with the External ID |
| `target-role-permissions-policy.json` | What the target role may do, using `terraform.tfvars.example`, plus the guardrail Deny |
| `sample-verify-output.txt` | What `python -m xacct verify` prints when everything is right. It was produced by the real code against scripted (stubbed) AWS answers |

The policy files show the shape Terraform builds. AWS may re-order keys or turn a one-item list into a
plain string when it stores them; that does not change their meaning.
