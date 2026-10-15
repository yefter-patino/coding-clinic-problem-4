import json

import pytest

from tests.helpers import (
    EXTERNAL_ID,
    PIPELINE_IDENTITY,
    SESSION,
    TARGET_IDENTITY,
    TARGET_ROLE_ARN,
    assume_ok,
    assume_params,
    identity,
    stubbed,
)
from xacct.verify import format_report, load_expectations, simulate, trust_checks


def run_trust_checks(script):
    """script(stub) adds the scripted AWS answers. The target-account STS client is stubbed too."""
    sts, stub = stubbed("sts")
    target_sts, target_stub = stubbed("sts")
    script(stub, target_stub)
    with stub, target_stub:
        checks = trust_checks(sts, TARGET_ROLE_ARN, EXTERNAL_ID, SESSION, lambda creds: target_sts)
    stub.assert_no_pending_responses()
    return checks


def denied(stub, external_id):
    stub.add_client_error(
        "assume_role",
        service_error_code="AccessDenied",
        http_status_code=403,
        expected_params=assume_params(external_id),
    )


def test_everything_passes_when_the_role_is_set_up_correctly():
    def script(stub, target_stub):
        stub.add_response("get_caller_identity", PIPELINE_IDENTITY, {})
        stub.add_response("assume_role", assume_ok(), assume_params(EXTERNAL_ID))
        target_stub.add_response("get_caller_identity", TARGET_IDENTITY, {})
        denied(stub, None)  # no External ID
        stub.add_client_error(  # wrong External ID (random, so match anything)
            "assume_role", service_error_code="AccessDenied", http_status_code=403
        )

    checks = run_trust_checks(script)
    assert [c.passed for c in checks] == [True] * 5
    assert "denied (AccessDenied)" in checks[3].detail


def test_a_trust_policy_without_the_external_id_condition_is_caught():
    def script(stub, target_stub):
        stub.add_response("get_caller_identity", PIPELINE_IDENTITY, {})
        stub.add_response("assume_role", assume_ok(), assume_params(EXTERNAL_ID))
        target_stub.add_response("get_caller_identity", TARGET_IDENTITY, {})
        stub.add_response("assume_role", assume_ok(), assume_params(None))  # should have been denied!
        stub.add_response("assume_role", assume_ok())

    checks = run_trust_checks(script)
    assert [c.passed for c in checks] == [True, True, True, False, False]
    assert "ALLOWED" in checks[3].detail


def test_negative_checks_are_inconclusive_when_the_correct_id_is_also_denied():
    def script(stub, target_stub):
        stub.add_response("get_caller_identity", PIPELINE_IDENTITY, {})
        denied(stub, EXTERNAL_ID)

    checks = run_trust_checks(script)
    assert [c.passed for c in checks] == [True, False, False, False]
    assert "inconclusive" in checks[2].detail


def test_landing_in_the_wrong_account_fails_check_3():
    def script(stub, target_stub):
        stub.add_response("get_caller_identity", PIPELINE_IDENTITY, {})
        stub.add_response("assume_role", assume_ok(), assume_params(EXTERNAL_ID))
        target_stub.add_response(
            "get_caller_identity",
            identity("arn:aws:sts::333333333333:assumed-role/yefter-cicd-deploy/x", "333333333333"),
            {},
        )
        denied(stub, None)
        stub.add_client_error("assume_role", service_error_code="AccessDenied", http_status_code=403)

    checks = run_trust_checks(script)
    assert checks[2].passed is False


def test_an_unexpected_error_is_not_counted_as_denied():
    def script(stub, target_stub):
        stub.add_response("get_caller_identity", PIPELINE_IDENTITY, {})
        stub.add_response("assume_role", assume_ok(), assume_params(EXTERNAL_ID))
        target_stub.add_response("get_caller_identity", TARGET_IDENTITY, {})
        stub.add_client_error("assume_role", service_error_code="Throttling", http_status_code=400)
        stub.add_client_error("assume_role", service_error_code="AccessDenied", http_status_code=403)

    checks = run_trust_checks(script)
    assert checks[3].passed is False
    assert "Throttling" in checks[3].detail


# ---------------------------------------------------------------- policy simulator
def sim_result(action, decision):
    return {"EvaluationResults": [{"EvalActionName": action, "EvalDecision": decision}], "IsTruncated": False}


def test_simulator_results_are_compared_with_expectations():
    iam, stub = stubbed("iam")
    bucket_object = "arn:aws:s3:::yefter-test-artifacts/app.zip"
    stub.add_response(
        "simulate_principal_policy",
        sim_result("s3:PutObject", "allowed"),
        {"PolicySourceArn": TARGET_ROLE_ARN, "ActionNames": ["s3:PutObject"], "ResourceArns": [bucket_object]},
    )
    stub.add_response(
        "simulate_principal_policy",
        sim_result("iam:CreateUser", "explicitDeny"),
        {"PolicySourceArn": TARGET_ROLE_ARN, "ActionNames": ["iam:CreateUser"]},
    )
    stub.add_response("simulate_principal_policy", sim_result("s3:DeleteObject", "allowed"))
    expectations = [
        {"action": "s3:PutObject", "resource": bucket_object, "expect": "allowed"},
        {"action": "iam:CreateUser", "expect": "denied"},
        {"action": "s3:DeleteObject", "resource": bucket_object, "expect": "denied"},
    ]
    with stub:
        checks = simulate(iam, TARGET_ROLE_ARN, expectations)
    assert [c.passed for c in checks] == [True, True, False]
    assert checks[2].detail == "allowed"


def test_load_expectations(tmp_path):
    good = tmp_path / "good.json"
    good.write_text(json.dumps({"checks": [{"action": "s3:PutObject", "expect": "allowed"}]}))
    assert load_expectations(good)[0]["action"] == "s3:PutObject"

    for bad in ({}, {"checks": []}, {"checks": [{"action": "s3:PutObject", "expect": "maybe"}]}):
        path = tmp_path / "bad.json"
        path.write_text(json.dumps(bad))
        with pytest.raises(ValueError):
            load_expectations(path)


def test_the_example_expectations_file_is_valid():
    assert len(load_expectations("config/expectations.example.json")) >= 3


def test_report_counts_passes_and_failures():
    from xacct.verify import Check

    report = format_report([Check("a", True, "ok"), Check("bb", False, "nope")])
    assert "[PASS] a " in report
    assert "[FAIL] bb" in report
    assert report.endswith("1 passed, 1 failed")
