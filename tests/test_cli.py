import json

import pytest

import xacct.cli as cli
from tests.helpers import (
    EXTERNAL_ID,
    PIPELINE_IDENTITY,
    TARGET_IDENTITY,
    TARGET_ROLE_ARN,
    assume_ok,
    assume_params,
    stubbed,
)


class FakeSession:
    """Stands in for boto3.Session: hands out pre-stubbed clients."""

    def __init__(self, clients):
        self.clients = clients

    def client(self, service):
        return self.clients[service]


@pytest.fixture
def aws(monkeypatch):
    """Scripted AWS for the CLI. Returns (pipeline_sts_stub, target_sts_stub, iam_stub, profiles_used)."""
    sts, sts_stub = stubbed("sts")
    target_sts, target_stub = stubbed("sts")
    iam, iam_stub = stubbed("iam")
    profiles = []

    def fake_make_session(profile="", region=""):
        profiles.append(profile)
        return FakeSession({"sts": sts, "iam": iam})

    monkeypatch.setattr(cli, "make_session", fake_make_session)
    monkeypatch.setattr(cli, "session_from_credentials", lambda creds, region: FakeSession({"sts": target_sts}))
    with sts_stub, target_stub, iam_stub:
        yield sts_stub, target_stub, iam_stub, profiles


def test_new_external_id_prints_a_valid_value(capsys):
    assert cli.main(["new-external-id", "--length", "40"]) == 0
    value = capsys.readouterr().out.strip()
    assert len(value) == 40


def test_assume_needs_the_external_id_in_the_environment(capsys):
    assert cli.main(["assume", "--role-arn", TARGET_ROLE_ARN]) == 1
    assert "XACCT_EXTERNAL_ID is empty" in capsys.readouterr().err


def test_assume_needs_a_role_arn():
    with pytest.raises(SystemExit) as stop:
        cli.main(["assume"])
    assert stop.value.code == 2  # argparse usage error


def test_assume_prints_export_lines(aws, monkeypatch, capsys):
    sts_stub, *_ = aws
    monkeypatch.setenv("XACCT_EXTERNAL_ID", EXTERNAL_ID)
    sts_stub.add_response("assume_role", assume_ok(), assume_params(EXTERNAL_ID))

    assert cli.main(["assume", "--role-arn", TARGET_ROLE_ARN]) == 0
    assert "export AWS_ACCESS_KEY_ID=ASIAEXAMPLEKEY000001" in capsys.readouterr().out


def test_assume_reads_role_and_external_id_from_custom_variables(aws, monkeypatch, capsys):
    sts_stub, *_ = aws
    monkeypatch.setenv("XACCT_ROLE_ARN", TARGET_ROLE_ARN)
    monkeypatch.setenv("PROD_EXTERNAL_ID", EXTERNAL_ID)
    sts_stub.add_response("assume_role", assume_ok(), assume_params(EXTERNAL_ID))

    assert cli.main(["assume", "--external-id-env", "PROD_EXTERNAL_ID", "--format", "credential-process"]) == 0
    assert json.loads(capsys.readouterr().out)["Version"] == 1


def test_assume_github_format_writes_the_env_file(aws, monkeypatch, tmp_path, capsys):
    sts_stub, *_ = aws
    env_file = tmp_path / "github_env"
    monkeypatch.setenv("GITHUB_ENV", str(env_file))
    monkeypatch.setenv("GITHUB_RUN_ID", "987654")
    monkeypatch.setenv("GITHUB_RUN_ATTEMPT", "1")
    monkeypatch.setenv("XACCT_EXTERNAL_ID", EXTERNAL_ID)
    params = assume_params(EXTERNAL_ID)
    params["RoleSessionName"] = "yefter-cicd-987654-1"
    sts_stub.add_response("assume_role", assume_ok(), params)

    assert cli.main(["assume", "--role-arn", TARGET_ROLE_ARN, "--format", "github"]) == 0
    out = capsys.readouterr().out
    assert "::add-mask::ASIAEXAMPLEKEY000001" in out
    assert "AWS_SESSION_TOKEN=token-value" in env_file.read_text()


def test_assume_github_format_outside_github_fails(aws, monkeypatch, capsys):
    sts_stub, *_ = aws
    monkeypatch.setenv("XACCT_EXTERNAL_ID", EXTERNAL_ID)
    sts_stub.add_response("assume_role", assume_ok(), assume_params(EXTERNAL_ID))

    assert cli.main(["assume", "--role-arn", TARGET_ROLE_ARN, "--format", "github"]) == 1
    assert "only works inside GitHub Actions" in capsys.readouterr().err


def test_access_denied_is_reported_cleanly(aws, monkeypatch, capsys):
    sts_stub, *_ = aws
    monkeypatch.setenv("XACCT_EXTERNAL_ID", EXTERNAL_ID)
    sts_stub.add_client_error("assume_role", service_error_code="AccessDenied", http_status_code=403)

    assert cli.main(["assume", "--role-arn", TARGET_ROLE_ARN]) == 1
    assert "AccessDenied" in capsys.readouterr().err


def add_good_trust_answers(sts_stub, target_stub):
    sts_stub.add_response("get_caller_identity", PIPELINE_IDENTITY, {})
    sts_stub.add_response("assume_role", assume_ok(), assume_params(EXTERNAL_ID))
    target_stub.add_response("get_caller_identity", TARGET_IDENTITY, {})
    sts_stub.add_client_error("assume_role", service_error_code="AccessDenied", http_status_code=403)
    sts_stub.add_client_error("assume_role", service_error_code="AccessDenied", http_status_code=403)


def test_verify_passes_with_exit_code_0(aws, monkeypatch, capsys):
    sts_stub, target_stub, _, _ = aws
    monkeypatch.setenv("XACCT_EXTERNAL_ID", EXTERNAL_ID)
    add_good_trust_answers(sts_stub, target_stub)

    assert cli.main(["verify", "--role-arn", TARGET_ROLE_ARN]) == 0
    assert "5 passed, 0 failed" in capsys.readouterr().out


def test_verify_with_expectations_uses_the_simulate_profile(aws, monkeypatch, tmp_path, capsys):
    sts_stub, target_stub, iam_stub, profiles = aws
    monkeypatch.setenv("XACCT_EXTERNAL_ID", EXTERNAL_ID)
    add_good_trust_answers(sts_stub, target_stub)
    iam_stub.add_response(
        "simulate_principal_policy",
        {"EvaluationResults": [{"EvalActionName": "iam:CreateUser", "EvalDecision": "allowed"}]},
    )
    expectations = tmp_path / "expectations.json"
    expectations.write_text(json.dumps({"checks": [{"action": "iam:CreateUser", "expect": "denied"}]}))

    code = cli.main(
        [
            "verify",
            "--role-arn",
            TARGET_ROLE_ARN,
            "--expectations",
            str(expectations),
            "--simulate-profile",
            "workload-admin",
        ]
    )
    assert code == 2  # a check failed
    assert profiles == ["", "workload-admin"]
    assert "[FAIL] iam:CreateUser on * is denied" in capsys.readouterr().out


def test_verify_policy_only_needs_no_external_id_and_no_pipeline_role(aws, tmp_path, capsys):
    _, _, iam_stub, profiles = aws
    iam_stub.add_response(
        "simulate_principal_policy",
        {"EvaluationResults": [{"EvalActionName": "iam:CreateUser", "EvalDecision": "explicitDeny"}]},
    )
    expectations = tmp_path / "expectations.json"
    expectations.write_text(json.dumps({"checks": [{"action": "iam:CreateUser", "expect": "denied"}]}))

    args = ["verify", "--role-arn", TARGET_ROLE_ARN, "--policy-only"]
    args += ["--expectations", str(expectations), "--simulate-profile", "workload-admin"]
    assert cli.main(args) == 0
    assert profiles == ["workload-admin"]  # the pipeline session was never created
    assert "1 passed, 0 failed" in capsys.readouterr().out


def test_verify_policy_only_without_expectations_is_a_usage_error():
    with pytest.raises(SystemExit) as stop:
        cli.main(["verify", "--role-arn", TARGET_ROLE_ARN, "--policy-only"])
    assert stop.value.code == 2


def test_verify_expectations_without_profile_is_a_usage_error(monkeypatch):
    monkeypatch.setenv("XACCT_EXTERNAL_ID", EXTERNAL_ID)
    with pytest.raises(SystemExit) as stop:
        cli.main(["verify", "--role-arn", TARGET_ROLE_ARN, "--expectations", "x.json"])
    assert stop.value.code == 2
