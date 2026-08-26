"""Tests for perfx/cluster_tool.py"""
import json
from unittest.mock import patch

import pytest

from perfx.cluster_tool import list_cluster_vms, fetch_cluster_vm_yaml


class TestListClusterVms:
    def test_parses_vm_list(self):
        fake_output = (
            "NAMESPACE          NAME              STATUS\n"
            "benchmark-runner   win-vm-1          Running\n"
            "default            linux-vm-2        Stopped\n"
        )
        with patch("perfx.cluster_tool._oc", return_value=(fake_output, 0, "")):
            result = list_cluster_vms()
        assert "vms" in result
        assert len(result["vms"]) == 2
        assert result["vms"][0]["name"] == "win-vm-1"
        assert result["vms"][0]["namespace"] == "benchmark-runner"
        assert result["vms"][1]["name"] == "linux-vm-2"

    def test_returns_error_on_failure(self):
        with patch("perfx.cluster_tool._oc", return_value=("", 1, "not logged in")):
            result = list_cluster_vms()
        assert "error" in result

    def test_empty_cluster(self):
        fake_output = "NAMESPACE   NAME   STATUS\n"
        with patch("perfx.cluster_tool._oc", return_value=(fake_output, 0, "")):
            result = list_cluster_vms()
        assert result["vms"] == []


class TestFetchClusterVmYaml:
    def test_saves_yaml_to_temp_file(self, tmp_path):
        fake_yaml = "apiVersion: kubevirt.io/v1\nkind: VirtualMachine\nmetadata:\n  name: win-vm-1\n"
        with patch("perfx.cluster_tool._oc", return_value=(fake_yaml, 0, "")):
            result = fetch_cluster_vm_yaml("win-vm-1", "benchmark-runner")
        assert "path" in result
        assert result["vm_name"] == "win-vm-1"
        assert result["namespace"] == "benchmark-runner"
        import pathlib
        content = pathlib.Path(result["path"]).read_text()
        assert "VirtualMachine" in content

    def test_returns_error_on_failure(self):
        with patch("perfx.cluster_tool._oc", return_value=("", 1, "not found")):
            result = fetch_cluster_vm_yaml("missing-vm", "default")
        assert "error" in result
