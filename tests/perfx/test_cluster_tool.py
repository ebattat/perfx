"""Tests for perfx/cluster_tool.py"""
import pathlib
import pytest
from unittest.mock import patch

from perfx.cluster_tool import list_cluster_vms, fetch_cluster_vm_yaml

RUNNING_OUTPUT = (
    "NAMESPACE          NAME              STATUS\n"
    "benchmark-runner   win-vm-1          Running\n"
    "default            linux-vm-2        Stopped\n"
)
EMPTY_OUTPUT = "NAMESPACE   NAME   STATUS\n"
FAKE_YAML = "apiVersion: kubevirt.io/v1\nkind: VirtualMachine\nmetadata:\n  name: win-vm-1\n"


@pytest.fixture
def oc_running():
    with patch("perfx.cluster_tool._oc", return_value=(RUNNING_OUTPUT, 0, "")) as m:
        yield m


@pytest.fixture
def oc_empty():
    with patch("perfx.cluster_tool._oc", return_value=(EMPTY_OUTPUT, 0, "")) as m:
        yield m


@pytest.fixture
def oc_error():
    with patch("perfx.cluster_tool._oc", return_value=("", 1, "not logged in")) as m:
        yield m


@pytest.fixture
def oc_yaml():
    with patch("perfx.cluster_tool._oc", return_value=(FAKE_YAML, 0, "")) as m:
        yield m


class TestListClusterVms:
    def test_parses_only_running_vms(self, oc_running):
        result = list_cluster_vms()
        assert len(result["vms"]) == 1
        assert result["vms"][0]["name"] == "win-vm-1"
        assert result["vms"][0]["namespace"] == "benchmark-runner"

    def test_returns_error_on_failure(self, oc_error):
        result = list_cluster_vms()
        assert "error" in result

    def test_empty_cluster(self, oc_empty):
        result = list_cluster_vms()
        assert result["vms"] == []


class TestFetchClusterVmYaml:
    def test_saves_yaml_to_temp_file(self, oc_yaml):
        result = fetch_cluster_vm_yaml("win-vm-1", "benchmark-runner")
        assert "path" in result
        assert result["vm_name"] == "win-vm-1"
        assert result["namespace"] == "benchmark-runner"
        assert "VirtualMachine" in pathlib.Path(result["path"]).read_text()

    def test_returns_error_on_failure(self, oc_error):
        result = fetch_cluster_vm_yaml("missing-vm", "default")
        assert "error" in result


class TestClusterIntegration:
    """Integration tests — skipped when oc is not logged in."""

    @pytest.fixture(autouse=True)
    def require_cluster(self):
        import subprocess
        try:
            result = subprocess.run(["oc", "whoami"], capture_output=True, timeout=5)
            if result.returncode != 0:
                pytest.skip("oc not logged in — skipping integration tests")
        except Exception:
            pytest.skip("oc not available — skipping integration tests")

    def test_list_cluster_vms_returns_dict(self):
        result = list_cluster_vms()
        assert "vms" in result or "error" in result

    def test_all_listed_vms_are_running(self):
        result = list_cluster_vms()
        if "vms" in result:
            for vm in result["vms"]:
                assert vm["status"].lower() == "running"
