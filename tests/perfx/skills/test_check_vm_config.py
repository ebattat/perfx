"""Tests for skills/check-vm-config/check_vm_config.py"""
import importlib.util
import subprocess
import sys
import textwrap
from pathlib import Path
from unittest.mock import patch

import pytest

SCRIPT = Path(__file__).parent.parent.parent.parent / "skills" / "check-vm-config" / "check_vm_config.py"
spec = importlib.util.spec_from_file_location("check_vm_config", SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

WINDOWS_YAML_ALL_ISSUES = textwrap.dedent("""\
    metadata:
      name: test-win-vm
    spec:
      template:
        spec:
          domain:
            clock:
              timezone: UTC
            devices:
              disks:
              - disk:
                  bus: virtio
                bootOrder: 1
              interfaces:
              - masquerade: {}
                model: virtio
              networkInterfaceMultiqueue: true
              tpm:
                enabled: false
            machine:
              type: pc-q35-rhel9.8.0
            firmware:
              bootloader:
                efi:
                  secureBoot: false
""")

WINDOWS_YAML_ALL_PASS = textwrap.dedent("""\
    metadata:
      name: test-win-vm
    spec:
      template:
        spec:
          domain:
            clock:
              timer:
                hpet:
                  present: false
                hyperv: {}
                pit:
                  tickPolicy: delay
                rtc:
                  tickPolicy: catchup
              utc: {}
            devices:
              autoattachMemBalloon: false
              blockMultiQueue: true
              tpm: {}
              networkInterfaceMultiqueue: true
              disks:
              - disk:
                  bus: virtio
                bootOrder: 1
              interfaces:
              - masquerade: {}
                model: virtio
            features:
              hyperv:
                ipi: {}
                synic: {}
                synictimer:
                  direct: {}
                spinlocks:
                  spinlocks: 8191
                reenlightenment: {}
                reset: {}
                relaxed: {}
                vpindex: {}
                runtime: {}
                tlbflush: {}
                frequencies: {}
                vapic: {}
            firmware:
              bootloader:
                efi:
                  secureBoot: false
            ioThreads:
              supplementalPoolThreadCount: 4
            ioThreadsPolicy: supplementalPool
            machine:
              type: pc-q35-rhel9.8.0
""")


class TestCheckFunction:
    def test_returns_tuple(self, tmp_path):
        f = tmp_path / "vm.yaml"
        f.write_text(WINDOWS_YAML_ALL_ISSUES)
        result = mod.check(str(f))
        assert isinstance(result, tuple)
        assert len(result) == 2
        report, corrected = result
        assert isinstance(report, str)

    def test_report_contains_audit_header(self, tmp_path):
        f = tmp_path / "vm.yaml"
        f.write_text(WINDOWS_YAML_ALL_ISSUES)
        report, _ = mod.check(str(f))
        assert "WINDOWS VM CONFIGURATION AUDIT" in report

    def test_report_contains_guest_steps(self, tmp_path):
        f = tmp_path / "vm.yaml"
        f.write_text(WINDOWS_YAML_ALL_ISSUES)
        report, _ = mod.check(str(f))
        assert "GUEST-SIDE STEPS" in report
        assert "bcdedit" in report

    def test_report_contains_recommendation(self, tmp_path):
        f = tmp_path / "vm.yaml"
        f.write_text(WINDOWS_YAML_ALL_ISSUES)
        report, _ = mod.check(str(f))
        assert "RECOMMENDATION" in report

    def test_corrected_yaml_returned_when_failures(self, tmp_path):
        f = tmp_path / "vm.yaml"
        f.write_text(WINDOWS_YAML_ALL_ISSUES)
        _, corrected = mod.check(str(f))
        assert corrected is not None
        assert "# Corrected YAML" in corrected
        assert "blockMultiQueue: true" in corrected

    def test_corrected_yaml_none_when_no_failures(self, tmp_path):
        f = tmp_path / "vm.yaml"
        f.write_text(WINDOWS_YAML_ALL_PASS)
        _, corrected = mod.check(str(f))
        assert corrected is None

    def test_corrected_yaml_is_valid_yaml(self, tmp_path):
        import yaml
        f = tmp_path / "vm.yaml"
        f.write_text(WINDOWS_YAML_ALL_ISSUES)
        _, corrected = mod.check(str(f))
        # strip comment lines and parse
        lines = [l for l in corrected.splitlines() if not l.strip().startswith("#")]
        content = "\n".join(lines)
        parsed = yaml.safe_load(content)
        assert parsed is not None
        assert "metadata" in parsed
