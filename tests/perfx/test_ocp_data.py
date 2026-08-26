"""Tests for skills/ocp-data/collect_ocp_data.py"""
import importlib.util
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

SCRIPT = Path(__file__).parent.parent.parent / "skills" / "ocp-data" / "collect_ocp_data.py"
spec = importlib.util.spec_from_file_location("collect_ocp_data", SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class TestToGib:
    def test_ki_large(self):
        assert mod._to_gib("524288000Ki") == "500Gi"

    def test_ki_nonzero_preserves_value(self):
        result = mod._to_gib("524288Ki")
        assert result != "0Gi"   # must not truncate nonzero values to 0
        assert "Gi" in result

    def test_gi(self):
        assert mod._to_gib("256Gi") == "256Gi"

    def test_mi(self):
        assert mod._to_gib("2048Mi") == "2Gi"

    def test_mi_fractional(self):
        result = mod._to_gib("1536Mi")
        assert result != "0Gi"
        assert "1.5Gi" in result or "Gi" in result

    def test_unknown(self):
        assert mod._to_gib("unknown") == "unknown"


class TestNodeData:
    def test_parses_worker_and_control_plane(self):
        fake_json = {
            "items": [
                {
                    "metadata": {
                        "name": "worker-0",
                        "labels": {}
                    },
                    "status": {
                        "capacity": {"cpu": "64", "memory": "262144Ki"},
                        "allocatable": {"cpu": "63", "memory": "258048Ki"},
                        "nodeInfo": {
                            "kernelVersion": "5.14.0",
                            "osImage": "Red Hat Enterprise Linux CoreOS 9.4"
                        }
                    }
                },
                {
                    "metadata": {
                        "name": "master-0",
                        "labels": {"node-role.kubernetes.io/control-plane": ""}
                    },
                    "status": {
                        "capacity": {"cpu": "16", "memory": "65536Ki"},
                        "allocatable": {"cpu": "15", "memory": "63488Ki"},
                        "nodeInfo": {
                            "kernelVersion": "5.14.0",
                            "osImage": "Red Hat Enterprise Linux CoreOS 9.4"
                        }
                    }
                }
            ]
        }
        import json
        with patch.object(mod, "run", return_value=(json.dumps(fake_json), 0)):
            nodes = mod.node_data()

        assert len(nodes) == 2
        worker = next(n for n in nodes if n["name"] == "worker-0")
        master = next(n for n in nodes if n["name"] == "master-0")
        assert worker["role"] == "worker"
        assert master["role"] == "control-plane"
        assert worker["cpu"] == "64"

    def test_returns_empty_on_error(self):
        with patch.object(mod, "run", return_value=("", 1)):
            nodes = mod.node_data()
        assert nodes == []


class TestVmCounts:
    def test_counts_vms_per_node(self):
        fake_json = {
            "items": [
                {"status": {"nodeName": "worker-0"}},
                {"status": {"nodeName": "worker-0"}},
                {"status": {"nodeName": "worker-1"}},
            ]
        }
        import json
        with patch.object(mod, "run", return_value=(json.dumps(fake_json), 0)):
            counts = mod.vm_counts()
        assert counts == {"worker-0": 2, "worker-1": 1}

    def test_returns_empty_on_error(self):
        with patch.object(mod, "run", return_value=("", 1)):
            counts = mod.vm_counts()
        assert counts == {}
