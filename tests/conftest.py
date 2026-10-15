import pytest


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch, tmp_path):
    """Fake AWS settings so no test can ever reach a real account, and no leftovers from your shell."""
    for name in list(__import__("os").environ):
        if name.startswith(("XACCT_", "GITHUB_", "AWS_")):
            monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    monkeypatch.setenv("AWS_CONFIG_FILE", str(tmp_path / "no-config"))
    monkeypatch.setenv("AWS_SHARED_CREDENTIALS_FILE", str(tmp_path / "no-credentials"))
