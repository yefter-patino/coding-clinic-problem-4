"""Shared test data. Account ids and keys here are fake."""

from datetime import datetime, timezone

import boto3
from botocore.stub import ANY, Stubber

TOOLING_ACCOUNT = "111111111111"
WORKLOAD_ACCOUNT = "222222222222"
PIPELINE_ROLE_ARN = f"arn:aws:iam::{TOOLING_ACCOUNT}:role/yefter-cicd-pipeline"
TARGET_ROLE_ARN = f"arn:aws:iam::{WORKLOAD_ACCOUNT}:role/yefter-cicd-deploy"
EXTERNAL_ID = "test-only-external-id-0123456789abcdef"
SESSION = "yefter-cicd-local"


def stubbed(service):
    """A real boto3 client whose answers we script with Stubber (no network)."""
    client = boto3.client(service, region_name="us-east-1")
    return client, Stubber(client)


def credentials(key="ASIAEXAMPLEKEY000001"):
    return {
        "AccessKeyId": key,
        "SecretAccessKey": "secret/with+special=chars",
        "SessionToken": "token-value",
        "Expiration": datetime(2026, 10, 14, 13, 0, tzinfo=timezone.utc),
    }


def assume_ok(role_arn=TARGET_ROLE_ARN):
    return {
        "Credentials": credentials(),
        "AssumedRoleUser": {
            "AssumedRoleId": "AROAEXAMPLEID:" + SESSION,
            "Arn": f"arn:aws:sts::{WORKLOAD_ACCOUNT}:assumed-role/{role_arn.rsplit('/', 1)[-1]}/{SESSION}",
        },
    }


def identity(arn, account):
    return {"UserId": "AROAEXAMPLEID:" + SESSION, "Account": account, "Arn": arn}


PIPELINE_IDENTITY = identity(
    f"arn:aws:sts::{TOOLING_ACCOUNT}:assumed-role/yefter-cicd-pipeline/GitHubActions", TOOLING_ACCOUNT
)
TARGET_IDENTITY = identity(
    f"arn:aws:sts::{WORKLOAD_ACCOUNT}:assumed-role/yefter-cicd-deploy/{SESSION}", WORKLOAD_ACCOUNT
)


def assume_params(external_id=EXTERNAL_ID, duration=900):
    params = {"RoleArn": TARGET_ROLE_ARN, "RoleSessionName": ANY, "DurationSeconds": duration}
    if external_id is not None:
        params["ExternalId"] = external_id
    return params
