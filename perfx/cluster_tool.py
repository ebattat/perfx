"""Tools for fetching live VM data from an OCP cluster via oc CLI."""
import subprocess
import tempfile
from pathlib import Path


def _oc(cmd, timeout=15):
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    return result.stdout.strip(), result.returncode, result.stderr.strip()


def list_cluster_vms() -> dict:
    """List all VMs running on the connected OCP cluster."""
    out, rc, err = _oc(
        ["oc", "get", "vm", "-A", "-o",
         "custom-columns=NAMESPACE:.metadata.namespace,NAME:.metadata.name,STATUS:.status.printableStatus"]
    )
    if rc != 0:
        return {"error": f"Cannot list VMs — is oc logged in? {err}"}
    lines = out.splitlines()
    vms = []
    for line in lines[1:]:  # skip header
        parts = line.split()
        if len(parts) >= 2:
            vms.append({"namespace": parts[0], "name": parts[1], "status": parts[2] if len(parts) > 2 else "unknown"})
    return {"vms": vms, "table": out}


def fetch_cluster_vm_yaml(name: str, namespace: str) -> dict:
    """Fetch a VM YAML from the cluster and save to a temp file. Returns the temp file path."""
    out, rc, err = _oc(["oc", "get", "vm", name, "-n", namespace, "-o", "yaml"])
    if rc != 0:
        return {"error": f"Cannot fetch VM '{name}' in namespace '{namespace}': {err}"}
    tmp = tempfile.NamedTemporaryFile(suffix=".yaml", mode="w", delete=False, prefix=f"vm_{name}_")
    tmp.write(out)
    tmp.close()
    return {"path": tmp.name, "vm_name": name, "namespace": namespace}
