"""Tests for skills/vm-config/check_qemu_hyperv.py"""
import importlib.util
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

SCRIPT = Path(__file__).parent.parent.parent.parent / "skills" / "qemu-hyperv" / "check_qemu_hyperv.py"
spec = importlib.util.spec_from_file_location("check_qemu_hyperv", SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

FULL_OUTPUT = """\
Starting pod/worker-1-debug ...
      1 hv-
      1 hv-frequencies=on
      1 hv-ipi=on
      1 hv-reenlightenment=on
      1 hv-relaxed=on
      1 hv-reset=on
      1 hv-runtime=on
      1 hv-spinlocks=0x1fff
      1 hv-stimer-direct=on
      1 hv-stimer=on
      1 hv-synic=on
      1 hv-time=on
      1 hv-tlbflush=on
      1 hv-vapic=on
      1 hv-vpindex=on
"""

MISSING_OUTPUT = """\
      1 hv-relaxed=on
      1 hv-reset=on
      1 hv-runtime=on
"""


class TestGetQemuHypervFlags:
    def test_parses_all_expected_flags(self):
        mock = type("R", (), {"returncode": 0, "stdout": FULL_OUTPUT})()
        with patch("subprocess.run", return_value=mock):
            flags = mod.get_qemu_hyperv_flags("worker-1")
        assert "hv-frequencies" in flags
        assert "hv-ipi" in flags
        assert "hv-spinlocks" in flags
        assert "hv-stimer-direct" in flags
        assert "hv-" not in flags  # bare hv- artifact excluded

    def test_returns_empty_on_failure(self):
        mock = type("R", (), {"returncode": 1, "stdout": ""})()
        with patch("subprocess.run", return_value=mock):
            flags = mod.get_qemu_hyperv_flags("worker-1")
        assert flags == []


WINDOWS_VMI_JSON = {
    "items": [{
        "metadata": {
            "name": "winmssql-vm-1",
            "labels": {"vm.kubevirt.io/os": "windows2k22"}
        },
        "status": {"nodeName": "worker-1"}
    }]
}

LINUX_VMI_JSON = {
    "items": [{
        "metadata": {
            "name": "fio-vm-1",
            "labels": {"vm.kubevirt.io/os": "rhel9"}
        },
        "status": {"nodeName": "worker-1"}
    }]
}


class TestGetWindowsVmsOnNode:
    def test_detects_windows_vm(self):
        import json
        mock = type("R", (), {"returncode": 0, "stdout": json.dumps(WINDOWS_VMI_JSON)})()
        with patch("subprocess.run", return_value=mock):
            vms = mod.get_windows_vms_on_node("worker-1")
        assert "winmssql-vm-1" in vms

    def test_skips_linux_vm(self):
        import json
        mock = type("R", (), {"returncode": 0, "stdout": json.dumps(LINUX_VMI_JSON)})()
        with patch("subprocess.run", return_value=mock):
            vms = mod.get_windows_vms_on_node("worker-1")
        assert vms == []


class TestCheckNode:
    def _mock_runs(self, vmi_json, qemu_output):
        import json
        calls = [
            type("R", (), {"returncode": 0, "stdout": json.dumps(vmi_json)})(),
            type("R", (), {"returncode": 0, "stdout": qemu_output})(),
        ]
        return calls

    def test_pass_when_all_flags_present(self):
        import json
        calls = self._mock_runs(WINDOWS_VMI_JSON, FULL_OUTPUT)
        with patch("subprocess.run", side_effect=calls):
            result = mod.check_node("worker-1")
        assert result["severity"] == "PASS"
        assert result["missing"] == []

    def test_fail_when_flags_missing(self):
        calls = self._mock_runs(WINDOWS_VMI_JSON, MISSING_OUTPUT)
        with patch("subprocess.run", side_effect=calls):
            result = mod.check_node("worker-1")
        assert result["severity"] == "FAIL"
        assert "hv-ipi" in result["missing"]

    def test_skip_when_no_windows_vm(self):
        import json
        mock = type("R", (), {"returncode": 0, "stdout": json.dumps(LINUX_VMI_JSON)})()
        with patch("subprocess.run", return_value=mock):
            result = mod.check_node("worker-1")
        assert result["severity"] == "SKIP"

    def test_fail_when_windows_vm_running_but_no_hv_flags(self):
        calls = self._mock_runs(WINDOWS_VMI_JSON, "")
        with patch("subprocess.run", side_effect=calls):
            result = mod.check_node("worker-1")
        assert result["severity"] == "FAIL"


class TestClusterIntegration:
    """Integration tests — skipped when oc is not logged in or no Windows VM running."""

    @pytest.fixture(autouse=True)
    def require_cluster(self):
        try:
            result = subprocess.run(["oc", "whoami"], capture_output=True, timeout=5)
            if result.returncode != 0:
                pytest.skip("oc not logged in")
        except Exception:
            pytest.skip("oc not available")

    def test_check_all_workers(self):
        nodes = mod.get_worker_nodes()
        if not nodes:
            pytest.skip("no worker nodes found")
        for node in nodes:
            result = mod.check_node(node)
            assert result["severity"] in ("PASS", "FAIL", "UNKNOWN", "SKIP")
            if result["severity"] == "PASS":
                assert result["missing"] == []
