"""Tests for skills/check-linux-vm-config/check_linux_vm_config.py"""
import importlib.util
import textwrap
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parent.parent.parent.parent.parent / "skills" / "check-linux-vm-config" / "check_linux_vm_config.py"
spec = importlib.util.spec_from_file_location("check_linux_vm_config", SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

LINUX_YAML_ISSUES = textwrap.dedent("""\
    metadata:
      name: test-linux-vm
    spec:
      template:
        spec:
          domain:
            devices:
              disks:
              - disk:
                  bus: virtio
                bootOrder: 1
              interfaces:
              - masquerade: {}
                model: virtio
""")

LINUX_YAML_PASS = textwrap.dedent("""\
    metadata:
      name: test-linux-vm
    spec:
      template:
        spec:
          evictionStrategy: LiveMigrate
          domain:
            devices:
              blockMultiQueue: true
              networkInterfaceMultiqueue: true
              disks:
              - disk:
                  bus: virtio
                  cache: none
                bootOrder: 1
              interfaces:
              - masquerade: {}
                model: virtio
            ioThreads:
              supplementalPoolThreadCount: 4
            ioThreadsPolicy: supplementalPool
""")


class TestCheckLinuxFunction:
    def test_report_contains_audit_header(self, tmp_path):
        f = tmp_path / "vm.yaml"
        f.write_text(LINUX_YAML_ISSUES)
        report = mod.check(str(f))
        assert "LINUX VM CONFIGURATION AUDIT" in report

    def test_report_contains_recommendation(self, tmp_path):
        f = tmp_path / "vm.yaml"
        f.write_text(LINUX_YAML_ISSUES)
        report = mod.check(str(f))
        assert "RECOMMENDATION" in report

    def test_fails_when_blockMultiQueue_missing(self, tmp_path):
        f = tmp_path / "vm.yaml"
        f.write_text(LINUX_YAML_ISSUES)
        report = mod.check(str(f))
        assert "❌" in report

    def test_passes_when_fully_configured(self, tmp_path):
        f = tmp_path / "vm.yaml"
        f.write_text(LINUX_YAML_PASS)
        report = mod.check(str(f))
        assert "0 critical issue(s)" in report

    def test_virtio_nic_not_checked_by_default(self, tmp_path):
        """NIC model check only runs if NIC.model is in rules file."""
        f = tmp_path / "vm.yaml"
        f.write_text(LINUX_YAML_ISSUES)
        report = mod.check(str(f))
        # NIC model not in current rules, but ioThreads checks are present
        assert "ioThreads" in report

    def test_eviction_strategy_optional_warning(self, tmp_path):
        f = tmp_path / "vm.yaml"
        f.write_text(LINUX_YAML_ISSUES)
        report = mod.check(str(f))
        assert "evictionStrategy" in report
        assert "⚠️" in report

    def test_warn_appears_in_recommendation_section(self, tmp_path):
        f = tmp_path / "vm.yaml"
        f.write_text(LINUX_YAML_ISSUES)
        report = mod.check(str(f))
        rec_section = report.split("RECOMMENDATION")[-1]
        assert "evictionStrategy" in rec_section or "⚠️" in rec_section
