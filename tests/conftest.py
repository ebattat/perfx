import os
import pytest


@pytest.fixture(scope="session", autouse=True)
def set_test_repos():
    """Ensure the benchmark-runner repo is always allowed during tests."""
    os.environ.setdefault("GIT_REPOS", "redhat-performance/benchmark-runner")
    if "your-org/your-repo" in os.environ.get("GIT_REPOS", ""):
        os.environ["GIT_REPOS"] = "redhat-performance/benchmark-runner"
