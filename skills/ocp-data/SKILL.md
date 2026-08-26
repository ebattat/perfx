# /ocp-data

Collect OCP cluster summary for issue investigation: versions, node count, per-node CPU, memory, kernel, OS, allocatable resources, and running VM count.

## Steps

1. Run the collection script:
   ```bash
   python3 skills/ocp-data/collect_ocp_data.py
   ```

2. Report the output table to the user

## Requirements

- `oc` CLI must be installed and logged into the cluster
- `kubectl` or `virtctl` not required

## Output

- Cluster summary: OCP version, CNV version, total nodes
- Node table: name, role, CPU, memory, allocatable CPU, allocatable memory, kernel, OS version, running VMs
