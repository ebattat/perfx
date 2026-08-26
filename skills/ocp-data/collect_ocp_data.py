#!/usr/bin/env python3
"""
Collect OCP cluster summary for issue investigation.
Requires: oc CLI logged into the cluster.
Usage: python3 collect_ocp_data.py
"""
import json
import subprocess
import sys


def run(cmd):
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
        return result.stdout.strip(), result.returncode
    except subprocess.TimeoutExpired:
        return "", 1


def ocp_version():
    out, rc = run("oc version -o json")
    if rc != 0:
        return "unknown"
    try:
        data = json.loads(out)
        return data.get("openshiftVersion", "unknown")
    except Exception:
        return "unknown"


def cnv_version():
    out, rc = run("oc get csv -n openshift-cnv -o json")
    if rc != 0:
        return "unknown"
    try:
        data = json.loads(out)
        for item in data.get("items", []):
            name = item.get("metadata", {}).get("name", "")
            if "kubevirt-hyperconverged" in name:
                return item.get("spec", {}).get("version", name)
        return "not installed"
    except Exception:
        return "unknown"


def node_data():
    out, rc = run("oc get nodes -o json")
    if rc != 0:
        print(f"ERROR: cannot get nodes — are you logged in? ({out})", file=sys.stderr)
        return []

    try:
        data = json.loads(out)
    except Exception:
        return []

    nodes = []
    for item in data.get("items", []):
        meta   = item.get("metadata", {})
        status = item.get("status", {})
        labels = meta.get("labels", {})

        name = meta.get("name", "unknown")

        # role
        role = "worker"
        if "node-role.kubernetes.io/control-plane" in labels or "node-role.kubernetes.io/master" in labels:
            role = "control-plane"

        # capacity
        capacity = status.get("capacity", {})
        cpu_cap  = capacity.get("cpu", "?")
        mem_cap  = _to_gib(capacity.get("memory", "0Ki"))

        # allocatable
        alloc     = status.get("allocatable", {})
        cpu_alloc = alloc.get("cpu", "?")
        mem_alloc = _to_gib(alloc.get("memory", "0Ki"))

        # kernel + OS
        node_info   = status.get("nodeInfo", {})
        kernel      = node_info.get("kernelVersion", "?")
        os_image    = node_info.get("osImage", "?")

        nodes.append({
            "name":      name,
            "role":      role,
            "cpu":       cpu_cap,
            "memory":    mem_cap,
            "alloc_cpu": cpu_alloc,
            "alloc_mem": mem_alloc,
            "kernel":    kernel,
            "os":        os_image,
        })

    return nodes


def vm_counts():
    out, rc = run("oc get vmi -A -o json")
    if rc != 0:
        return {}
    try:
        data = json.loads(out)
        counts = {}
        for item in data.get("items", []):
            node = item.get("status", {}).get("nodeName", "")
            if node:
                counts[node] = counts.get(node, 0) + 1
        return counts
    except Exception:
        return {}


def _to_gib(mem_str):
    """Convert a Kubernetes memory quantity to a human-readable GiB string."""
    try:
        if mem_str.endswith("Ki"):
            gib = int(mem_str[:-2]) / (1024 * 1024)
        elif mem_str.endswith("Mi"):
            gib = int(mem_str[:-2]) / 1024
        elif mem_str.endswith("Gi"):
            return mem_str
        else:
            return mem_str
        return f"{gib:.1f}Gi" if gib != int(gib) else f"{int(gib)}Gi"
    except Exception:
        return mem_str


def print_table(nodes, counts):
    col = [28, 14, 8, 10, 14, 14, 22, 16, 10]
    headers = ["Node", "Role", "CPU", "Memory", "Alloc CPU", "Alloc Mem", "Kernel", "OS", "VMs"]
    sep = "─" * sum(col)

    def row(*vals):
        return "  " + "".join(str(v)[:col[i]].ljust(col[i]) for i, v in enumerate(vals))

    print(sep)
    print(row(*headers))
    print(sep)
    for n in nodes:
        vms = counts.get(n["name"], 0)
        os_short = n["os"].replace("Red Hat Enterprise Linux CoreOS ", "RHCOS ")
        print(row(n["name"], n["role"], n["cpu"], n["memory"],
                  n["alloc_cpu"], n["alloc_mem"], n["kernel"], os_short, vms))
    print(sep)


def main():
    """Collect OCP cluster data and print a structured report."""
    print("\nCollecting OCP cluster data...\n")

    ocpv = ocp_version()
    cnvv = cnv_version()
    nodes = node_data()
    counts = vm_counts()

    if not nodes:
        print("SEVERITY: UNKNOWN")
        print("\nFINDINGS:")
        print("  - Could not retrieve node data (oc not logged in or unavailable)")
        print("\nRECOMMENDATION:")
        print("  - Log in to the cluster: oc login <cluster-url>")
        print("\nSUMMARY: No cluster data available.")
        return

    findings = []
    if "ec." in ocpv or "alpha" in ocpv or "beta" in ocpv:
        findings.append(f"OCP {ocpv} is a pre-release version")

    kernels = {n["kernel"] for n in nodes}
    if len(kernels) > 1:
        findings.append("Mixed kernel versions across nodes")

    os_versions = {n["os"] for n in nodes}
    if len(os_versions) > 1:
        findings.append("Mixed OS versions across nodes")

    severity = "WARNING" if findings else "PASS"

    print("=" * 50)
    print(f"  OCP Version    {ocpv}")
    print(f"  CNV Version    {cnvv}")
    print(f"  Total Nodes    {len(nodes)}")
    print(f"  Total VMs      {sum(counts.values())}")
    print("=" * 50)
    print()

    print_table(nodes, counts)
    print()

    print(f"SEVERITY: {severity}")
    print("\nFINDINGS:")
    if findings:
        for f in findings:
            print(f"  - {f}")
    else:
        print("  - No issues detected")

    print("\nRECOMMENDATION:")
    if "pre-release" in " ".join(findings):
        print("  - Upgrade to a stable OCP release for production workloads")
    elif "Mixed kernel" in " ".join(findings) or "Mixed OS" in " ".join(findings):
        print("  - Update all nodes to the same version before investigating performance issues")
    else:
        print("  - Cluster looks healthy")

    workers = [n for n in nodes if n["role"] == "worker"]
    print(f"\nSUMMARY: {len(nodes)} nodes ({len(workers)} workers), "
          f"{sum(counts.values())} VMs running, severity: {severity}")


if __name__ == "__main__":
    main()
