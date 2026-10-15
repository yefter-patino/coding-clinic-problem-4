"""Prove the cross-account setup works AND is locked down.

Part 1, the trust checks (run with the PIPELINE role's credentials):
  1. Who am I?                                 (should be the pipeline role)
  2. Assume the target role WITH the External ID     -> must work
  3. Who am I in the target account?           (should be the target role)
  4. Assume it WITHOUT the External ID         -> must be denied
  5. Assume it with a WRONG External ID        -> must be denied

Part 2, least privilege (optional, run with an admin/auditor profile in the WORKLOAD account):
  Ask IAM's policy simulator about a list of actions and compare with what you expect.
"""

import json
from dataclasses import dataclass

from botocore.exceptions import ClientError

from xacct.assume import account_of, assume_role, role_name_of
from xacct.external_id import generate

DENIED_CODES = {"AccessDenied", "AccessDeniedException"}


@dataclass
class Check:
    name: str
    passed: bool
    detail: str = ""


def _try_assume(sts, role_arn, session_name, external_id=None):
    """Returns ('ok', credentials) or ('denied', code) or ('error', code). Never raises ClientError."""
    request = {"RoleArn": role_arn, "RoleSessionName": session_name, "DurationSeconds": 900}
    if external_id is not None:
        request["ExternalId"] = external_id
    try:
        return "ok", sts.assume_role(**request)["Credentials"]
    except ClientError as err:
        code = err.response["Error"]["Code"]
        return ("denied" if code in DENIED_CODES else "error"), code


def trust_checks(sts, role_arn, external_id, session_name, sts_for_credentials):
    """Run checks 1-5. sts_for_credentials(creds) must return an STS client that uses those credentials."""
    checks = []

    me = sts.get_caller_identity()
    checks.append(Check("1. caller identity", True, me["Arn"]))

    # 2 + 3: the happy path.
    try:
        creds = assume_role(sts, role_arn, external_id, session_name)
        checks.append(Check("2. assume WITH the External ID is allowed", True, "allowed"))
    except ClientError as err:
        creds = None
        checks.append(Check("2. assume WITH the External ID is allowed", False, err.response["Error"]["Code"]))

    if creds:
        there = sts_for_credentials(creds).get_caller_identity()
        expected = f":assumed-role/{role_name_of(role_arn)}/"
        same_account = there["Account"] == account_of(role_arn)
        checks.append(
            Check(
                "3. identity in the target account",
                same_account and expected in there["Arn"],
                there["Arn"],
            )
        )

    # 4 + 5: the doors that must stay shut. They only mean something if check 2 worked:
    # a denial is no proof of the External ID when the correct one is denied too.
    negative = [
        ("4. assume WITHOUT the External ID is denied", None),
        ("5. assume with a WRONG External ID is denied", generate(48)),
    ]
    for name, value in negative:
        if not creds:
            checks.append(Check(name, False, "inconclusive: check 2 failed, fix that first"))
            continue
        outcome, info = _try_assume(sts, role_arn, session_name, value)
        if outcome == "denied":
            checks.append(Check(name, True, f"denied ({info})"))
        elif outcome == "ok":
            checks.append(Check(name, False, "ALLOWED: the trust policy does not require the External ID"))
        else:
            checks.append(Check(name, False, f"unexpected error {info}"))
    return checks


# ---------------------------------------------------------------- least privilege
def load_expectations(path):
    """Read the expectations file. Each check: action, expect (allowed/denied), optional resource."""
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
    items = data.get("checks")
    if not isinstance(items, list) or not items:
        raise ValueError(f"{path}: needs a non-empty 'checks' list")
    for number, item in enumerate(items, start=1):
        if "action" not in item or item.get("expect") not in ("allowed", "denied"):
            raise ValueError(f"{path}: check {number} needs 'action' and 'expect' (allowed or denied)")
    return items


def simulate(iam, role_arn, expectations):
    """Ask the IAM policy simulator about each action, compare with the expectation."""
    checks = []
    for item in expectations:
        request = {"PolicySourceArn": role_arn, "ActionNames": [item["action"]]}
        if item.get("resource"):
            request["ResourceArns"] = [item["resource"]]
        result = iam.simulate_principal_policy(**request)["EvaluationResults"][0]
        decision = result["EvalDecision"]  # allowed, explicitDeny or implicitDeny
        got = "allowed" if decision == "allowed" else "denied"
        target = item.get("resource", "*")
        checks.append(
            Check(
                f"{item['action']} on {target} is {item['expect']}",
                got == item["expect"],
                decision,
            )
        )
    return checks


def format_report(checks):
    width = max(len(c.name) for c in checks)
    lines = [f"[{'PASS' if c.passed else 'FAIL'}] {c.name.ljust(width)}  {c.detail}" for c in checks]
    failed = sum(1 for c in checks if not c.passed)
    lines.append(f"{len(checks) - failed} passed, {failed} failed")
    return "\n".join(lines)
