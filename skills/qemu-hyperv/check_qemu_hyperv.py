#!/usr/bin/env python3
"""
Verify hyperv enlightenments are applied to the running QEMU process on an OCP node.

Windows VMs only — Linux VMs do not use hyperv enlightenments.

Usage:
  python3 check_qemu_hyperv.py --node <node-name>
  python3 check_qemu_hyperv.py --all         # check all worker nodes

Requires: oc CLI logged into the cluster and a Windows VM running on the target node.
"""
import subprocess
import sys
import argparse
from pathlib import Path

LOGS_DIR = Path(__file__).parent.parent.parent / "logs"

EXPECTED_FLAGS = {
    "hv-frequencies",
    "hv-ipi",
    "hv-reenlightenment",
    "hv-relaxed",
    "hv-reset",
    "hv-runtime",
    "hv-spinlocks",
    "hv-stimer-direct",
    "hv-stimer",
    "hv-synic",
    "hv-time",
    "hv-tlbflush",
    "hv-vapic",
    "hv-vpindex",
}


def get_worker_nodes() -> list:
    """Return list of worker node names."""
    result = subprocess.run(
        ["oc", "get", "nodes", "-l", "node-role.kubernetes.io/worker",
         "-o", "custom-columns=NAME:.metadata.name", "--no-headers"],
        capture_output=True, text=True, timeout=15
    )
    if result.returncode != 0:
        return []
    return [n.strip() for n in result.stdout.splitlines() if n.strip()]


def get_qemu_hyperv_flags(node: str) -> list:
    """Run oc debug on node and extract hv- flags from QEMU process."""
    cmd = (
        'ps -eaf | grep qemu-kvm | sed -e \'s/,/ /g\' | '
        'xargs -n1 | grep hv- | sort | uniq -c'
    )
    result = subprocess.run(
        ["oc", "debug", f"node/{node}", "--",
         "chroot", "/host", "bash", "-c", cmd],
        capture_output=True, text=True, timeout=120
    )
    if result.returncode != 0:
        return []

    flags = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) >= 2:
            flag = parts[1].split("=")[0]  # strip =on or =0x1fff
            if flag.startswith("hv-") and flag != "hv-":
                flags.append(flag)
    return flags


def get_windows_vms_on_node(node: str) -> list:
    """Return names of Windows VMIs running on this node.

    Detects Windows by:
    1. vm.kubevirt.io/os label containing 'windows'
    2. vm.kubevirt.io/os label containing 'win'
    """
    result = subprocess.run(
        ["oc", "get", "vmi", "-A", "-o", "json"],
        capture_output=True, text=True, timeout=15
    )
    if result.returncode != 0:
        return []
    import json
    try:
        data = json.loads(result.stdout)
    except Exception:
        return []
    windows_vms = []
    for item in data.get("items", []):
        if item.get("status", {}).get("nodeName") != node:
            continue
        labels = item.get("metadata", {}).get("labels", {})
        os_label = labels.get("vm.kubevirt.io/os", "").lower()
        name = item.get("metadata", {}).get("name", "")
        if "win" in os_label:
            windows_vms.append(name)
    return windows_vms


def check_node(node: str) -> dict:
    """Check a single node and return findings."""
    print(f"Checking node: {node} ...", flush=True)

    windows_vms = get_windows_vms_on_node(node)
    if not windows_vms:
        return {
            "node": node,
            "severity": "SKIP",
            "found": [],
            "missing": [],
            "extra": [],
            "error": "No Windows VM running on this node — skipping (Linux VMs do not use hyperv)",
        }

    print(f"  Windows VMs found: {', '.join(windows_vms)}", flush=True)
    found = get_qemu_hyperv_flags(node)

    if not found:
        return {
            "node": node,
            "severity": "FAIL",
            "found": [],
            "missing": sorted(EXPECTED_FLAGS),
            "extra": [],
            "error": f"Windows VM(s) running ({', '.join(windows_vms)}) but no hv- flags in QEMU — hyperv not applied",
        }

    found_set   = set(found)
    missing     = sorted(EXPECTED_FLAGS - found_set)
    extra       = sorted(found_set - EXPECTED_FLAGS)
    severity    = "PASS" if not missing else "FAIL"

    return {
        "node":     node,
        "severity": severity,
        "found":    sorted(found_set),
        "missing":  missing,
        "extra":    extra,
        "error":    None,
    }


def print_report(result: dict) -> None:
    sep = "=" * 60
    print(f"\n{sep}")
    print(f"QEMU Hyperv Check — {result['node']}")
    print(sep)
    print(f"SEVERITY: {result['severity']}")

    if result.get("error"):
        print(f"\nFINDINGS:\n  - {result['error']}")
        if result["severity"] == "SKIP":
            print(f"\nSUMMARY: Skipped — no Windows VM running on this node.")
        else:
            print(f"\nRECOMMENDATION:\n  - Ensure a Windows VM is running on this node")
            print(f"\nSUMMARY: Could not verify — no QEMU process found.")
        return

    print("\nFINDINGS:")
    for flag in result["found"]:
        print(f"  ✅  {flag}")
    for flag in result["missing"]:
        print(f"  ❌  {flag} — MISSING from QEMU process")
    for flag in result["extra"]:
        print(f"  ℹ️   {flag} — present but not in expected set")

    print("\nRECOMMENDATION:")
    if result["missing"]:
        print("  - Check VM YAML has all hyperv enlightenments configured")
        print("  - Reference: rules/windows-vm-template.yaml")
    else:
        print("  - All hyperv enlightenments correctly applied")

    total = len(EXPECTED_FLAGS)
    found_count = total - len(result["missing"])
    print(f"\nSUMMARY: {found_count}/{total} flags present on {result['node']}, "
          f"severity: {result['severity']}")


def main():
    parser = argparse.ArgumentParser(
        description="Verify hyperv enlightenments in QEMU process on OCP nodes"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--node", help="Specific node name to check")
    group.add_argument("--all",  action="store_true", help="Check all worker nodes")
    args = parser.parse_args()

    nodes = [args.node] if args.node else get_worker_nodes()
    if not nodes:
        print("ERROR: no worker nodes found — is oc logged in?", file=sys.stderr)
        sys.exit(1)

    results = [check_node(n) for n in nodes]
    for r in results:
        print_report(r)

    checked = [r for r in results if r["severity"] != "SKIP"]
    if not checked:
        print("\nNo Windows VMs found running on any worker node.")
        sys.exit(0)
    failed = [r for r in results if r["severity"] == "FAIL"]
    if failed:
        sys.exit(2)


if __name__ == "__main__":
    main()
