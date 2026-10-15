"""Command line for xacct.

  python -m xacct new-external-id
  python -m xacct assume --role-arn ARN [--format env|github|credential-process]
  python -m xacct verify --role-arn ARN [--expectations FILE --simulate-profile PROFILE]

The External ID is read from an environment variable (XACCT_EXTERNAL_ID by default),
never from the command line, because command lines end up in logs and shell history.
"""

import argparse
import os
import sys

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from xacct import __version__
from xacct.assume import (
    as_credential_process,
    as_env_lines,
    assume_role,
    make_session_name,
    write_github_env,
)
from xacct.external_id import generate, validate
from xacct.verify import format_report, load_expectations, simulate, trust_checks

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_CHECKS_FAILED = 2


def env(name, default=""):
    return os.environ.get(name, default)


def make_session(profile="", region=""):
    """A boto3 session. Empty values mean "use the normal AWS defaults"."""
    return boto3.Session(profile_name=profile or None, region_name=region or None)


def session_from_credentials(creds, region):
    return boto3.Session(
        aws_access_key_id=creds["AccessKeyId"],
        aws_secret_access_key=creds["SecretAccessKey"],
        aws_session_token=creds["SessionToken"],
        region_name=region or None,
    )


def read_external_id(variable):
    value = os.environ.get(variable, "")
    if not value:
        raise ValueError(f"environment variable {variable} is empty: put the External ID there")
    return validate(value)


# ---------------------------------------------------------------- parser
def add_role_options(parser):
    parser.add_argument("--role-arn", default=env("XACCT_ROLE_ARN"), help="target role ARN (env XACCT_ROLE_ARN)")
    parser.add_argument(
        "--external-id-env",
        default="XACCT_EXTERNAL_ID",
        help="name of the environment variable that holds the External ID (default XACCT_EXTERNAL_ID)",
    )
    parser.add_argument("--profile", default=env("XACCT_PROFILE"), help="AWS profile to start from (empty in CI)")
    parser.add_argument("--region", default=env("AWS_REGION"), help="AWS region (env AWS_REGION)")
    parser.add_argument(
        "--name-prefix",
        default=env("XACCT_NAME_PREFIX", "yefter"),
        help="prefix for the role session name (default yefter)",
    )


def build_parser():
    parser = argparse.ArgumentParser(prog="xacct", description=__doc__.split("\n\n")[0])
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)

    new = commands.add_parser("new-external-id", help="print a new random External ID")
    new.add_argument("--length", type=int, default=48, help="number of characters (32-1224, default 48)")

    assume = commands.add_parser("assume", help="assume the target role and output the credentials")
    add_role_options(assume)
    assume.add_argument(
        "--format",
        choices=["env", "github", "credential-process"],
        default="env",
        help="env = export lines, github = write to $GITHUB_ENV, credential-process = JSON for an AWS profile",
    )
    assume.add_argument("--duration", type=int, default=900, help="session length in seconds, 900-3600 (default 900)")

    verify = commands.add_parser("verify", help="prove the External ID is required and the policy is tight")
    add_role_options(verify)
    verify.add_argument("--expectations", default="", help="JSON file of actions expected allowed/denied")
    verify.add_argument(
        "--simulate-profile",
        default=env("XACCT_SIMULATE_PROFILE"),
        help="admin/auditor profile in the WORKLOAD account, used for the policy simulator",
    )
    verify.add_argument(
        "--policy-only",
        action="store_true",
        help="skip the trust checks (they need the pipeline role) and only run the policy simulator",
    )
    return parser


# ---------------------------------------------------------------- commands
def session_name(args):
    return make_session_name(args.name_prefix, env("GITHUB_RUN_ID"), env("GITHUB_RUN_ATTEMPT"))


def run_new_external_id(args):
    print(generate(args.length))
    return EXIT_OK


def run_assume(args, parser):
    if not args.role_arn:
        parser.error("--role-arn is required (or set XACCT_ROLE_ARN)")
    external_id = read_external_id(args.external_id_env)
    sts = make_session(args.profile, args.region).client("sts")
    creds = assume_role(sts, args.role_arn, external_id, session_name(args), args.duration)

    if args.format == "github":
        env_file = env("GITHUB_ENV")
        if not env_file:
            raise ValueError("--format github only works inside GitHub Actions (GITHUB_ENV is not set)")
        write_github_env(creds, env_file)
        print(
            f"Assumed {args.role_arn}. Credentials are available to the next steps (valid until {creds['Expiration']})."
        )
    elif args.format == "credential-process":
        print(as_credential_process(creds))
    else:
        print(as_env_lines(creds))
    return EXIT_OK


def run_verify(args, parser):
    if not args.role_arn:
        parser.error("--role-arn is required (or set XACCT_ROLE_ARN)")
    if args.expectations and not args.simulate_profile:
        parser.error("--expectations needs --simulate-profile (an admin/auditor profile in the workload account)")
    if args.policy_only and not args.expectations:
        parser.error("--policy-only needs --expectations and --simulate-profile")

    checks = []
    if not args.policy_only:
        external_id = read_external_id(args.external_id_env)
        sts = make_session(args.profile, args.region).client("sts")
        checks += trust_checks(
            sts,
            args.role_arn,
            external_id,
            session_name(args),
            lambda creds: session_from_credentials(creds, args.region).client("sts"),
        )

    if args.expectations:
        iam = make_session(args.simulate_profile, args.region).client("iam")
        checks += simulate(iam, args.role_arn, load_expectations(args.expectations))

    print(format_report(checks))
    return EXIT_OK if all(c.passed for c in checks) else EXIT_CHECKS_FAILED


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "new-external-id":
            return run_new_external_id(args)
        if args.command == "assume":
            return run_assume(args, parser)
        return run_verify(args, parser)
    except (ClientError, BotoCoreError, ValueError, OSError) as err:
        print(f"error: {err}", file=sys.stderr)
        return EXIT_ERROR
