"""Assume the target role (with the External ID) and hand the credentials to the next step."""

import json
import re
import shlex

# Role session names may only use letters, digits and _ + = , . @ -  (2-64 characters).
_BAD_SESSION_CHARS = re.compile(r"[^A-Za-z0-9_+=,.@-]")
_ROLE_ARN = re.compile(r"^arn:aws[a-z-]*:iam::(\d{12}):role/[A-Za-z0-9+=,.@_/-]+$")

# The pipeline is already using a role (from GitHub OIDC), so this is "role chaining".
# AWS limits a chained session to one hour.
MIN_DURATION = 900
MAX_CHAINED_DURATION = 3600


def account_of(role_arn):
    """'arn:aws:iam::123456789012:role/x' -> '123456789012'. Raises ValueError if the ARN is wrong."""
    match = _ROLE_ARN.match(role_arn or "")
    if not match:
        raise ValueError(f"not an IAM role ARN: {role_arn!r}")
    return match.group(1)


def role_name_of(role_arn):
    """'arn:aws:iam::123456789012:role/path/name' -> 'name'."""
    return role_arn.rsplit("/", 1)[-1]


def make_session_name(prefix, run_id="", attempt=""):
    """A readable session name, for example yefter-cicd-123456789-1.

    It shows up in CloudTrail in the target account, so you can see which pipeline run did what.
    """
    parts = [prefix, "cicd", run_id or "local"]
    if attempt:
        parts.append(attempt)
    name = _BAD_SESSION_CHARS.sub("-", "-".join(parts))[:64]
    return name if len(name) >= 2 else "xacct"


def assume_role(sts, role_arn, external_id, session_name, duration_seconds=MIN_DURATION):
    """Call STS AssumeRole with the External ID. Returns the Credentials dict from AWS."""
    account_of(role_arn)  # fail early with a clear message
    if not MIN_DURATION <= duration_seconds <= MAX_CHAINED_DURATION:
        raise ValueError(f"duration must be {MIN_DURATION}-{MAX_CHAINED_DURATION} seconds (role chaining limit)")
    response = sts.assume_role(
        RoleArn=role_arn,
        RoleSessionName=session_name,
        ExternalId=external_id,
        DurationSeconds=duration_seconds,
    )
    return response["Credentials"]


# ---------------------------------------------------------------- output formats
def _pairs(creds):
    return [
        ("AWS_ACCESS_KEY_ID", creds["AccessKeyId"]),
        ("AWS_SECRET_ACCESS_KEY", creds["SecretAccessKey"]),
        ("AWS_SESSION_TOKEN", creds["SessionToken"]),
    ]


def as_env_lines(creds):
    """Shell lines for a laptop:  eval "$(python -m xacct assume ...)" """
    return "\n".join(f"export {key}={shlex.quote(value)}" for key, value in _pairs(creds))


def write_github_env(creds, env_file, echo=print):
    """GitHub Actions: hide the values in the logs, then make them available to the next steps."""
    for _, value in _pairs(creds):
        echo(f"::add-mask::{value}")
    with open(env_file, "a", encoding="utf-8") as handle:
        for key, value in _pairs(creds):
            handle.write(f"{key}={value}\n")


def as_credential_process(creds):
    """JSON for an AWS CLI profile's credential_process setting."""
    return json.dumps(
        {
            "Version": 1,
            "AccessKeyId": creds["AccessKeyId"],
            "SecretAccessKey": creds["SecretAccessKey"],
            "SessionToken": creds["SessionToken"],
            "Expiration": creds["Expiration"].isoformat(),
        }
    )
