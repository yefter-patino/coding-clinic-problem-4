import json
import shlex

import pytest

from tests.helpers import EXTERNAL_ID, TARGET_ROLE_ARN, assume_ok, assume_params, credentials, stubbed
from xacct.assume import (
    account_of,
    as_credential_process,
    as_env_lines,
    assume_role,
    make_session_name,
    role_name_of,
    write_github_env,
)


def test_account_and_name_are_read_from_the_arn():
    assert account_of(TARGET_ROLE_ARN) == "222222222222"
    assert role_name_of("arn:aws:iam::222222222222:role/cicd/yefter-cicd-deploy") == "yefter-cicd-deploy"
    assert account_of("arn:aws-us-gov:iam::222222222222:role/x") == "222222222222"


@pytest.mark.parametrize(
    "bad",
    ["", "*", "arn:aws:iam::222222222222:root", "arn:aws:iam::2222:role/x", "arn:aws:iam::222222222222:role/*"],
)
def test_bad_role_arns_are_refused(bad):
    with pytest.raises(ValueError, match="not an IAM role ARN"):
        account_of(bad)


def test_session_name_is_cleaned_and_limited_to_64_characters():
    assert make_session_name("yefter", "123", "2") == "yefter-cicd-123-2"
    assert make_session_name("yefter") == "yefter-cicd-local"
    assert make_session_name("bad name!", "run#1") == "bad-name--cicd-run-1"
    assert len(make_session_name("y" * 100, "1")) == 64


def test_assume_role_sends_the_external_id():
    sts, stub = stubbed("sts")
    stub.add_response("assume_role", assume_ok(), assume_params(EXTERNAL_ID, 900))
    with stub:
        creds = assume_role(sts, TARGET_ROLE_ARN, EXTERNAL_ID, "yefter-cicd-local")
    stub.assert_no_pending_responses()
    assert creds["AccessKeyId"] == "ASIAEXAMPLEKEY000001"


@pytest.mark.parametrize("duration", [899, 3601, 43200])
def test_duration_outside_the_role_chaining_limit_is_refused(duration):
    sts, _ = stubbed("sts")
    with pytest.raises(ValueError, match="role chaining"):
        assume_role(sts, TARGET_ROLE_ARN, EXTERNAL_ID, "s1", duration)


def test_env_lines_are_shell_safe():
    lines = as_env_lines(credentials()).splitlines()
    assert lines[0] == "export AWS_ACCESS_KEY_ID=ASIAEXAMPLEKEY000001"
    # the secret contains + / = so it must be quoted, and must survive a round trip through the shell
    assert shlex.split(lines[1].split("=", 1)[1]) == ["secret/with+special=chars"]


def test_github_output_masks_values_before_writing_them(tmp_path):
    env_file = tmp_path / "github_env"
    echoed = []
    write_github_env(credentials(), str(env_file), echo=echoed.append)

    assert echoed == [
        "::add-mask::ASIAEXAMPLEKEY000001",
        "::add-mask::secret/with+special=chars",
        "::add-mask::token-value",
    ]
    assert env_file.read_text().splitlines() == [
        "AWS_ACCESS_KEY_ID=ASIAEXAMPLEKEY000001",
        "AWS_SECRET_ACCESS_KEY=secret/with+special=chars",
        "AWS_SESSION_TOKEN=token-value",
    ]


def test_credential_process_json_has_the_fields_the_aws_cli_needs():
    data = json.loads(as_credential_process(credentials()))
    assert data["Version"] == 1
    assert data["Expiration"] == "2026-10-14T13:00:00+00:00"
    assert {"AccessKeyId", "SecretAccessKey", "SessionToken"} <= data.keys()
