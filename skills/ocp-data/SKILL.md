# /ocp-data

Analyze pre-collected OCP cluster data for issue investigation: versions, node count, per-node CPU, memory, kernel, OS version, and running VM count.

## Steps

1. Collect local artifacts from the cluster:
   ```bash
   oc get nodes -o json > nodes.json
   oc version -o json  > version.json
   oc get vmi -A -o json > vmis.json
   ```

2. Run the analysis script on the local files:
   ```bash
   python3 skills/ocp-data/collect_ocp_data.py \
     --nodes nodes.json \
     --version version.json \
     --vmis vmis.json
   ```

3. Report the output to the user

## Output Sections

- Cluster summary table: OCP version, CNV version, node count, VM count
- Node table: name, role, CPU, memory, allocatable CPU/memory, kernel, OS, running VMs
- SEVERITY: PASS or WARNING
- FINDINGS: list of detected issues
- RECOMMENDATION: what to fix
- SUMMARY: one-line verdict

## Notes

- `--version` and `--vmis` are optional — only `--nodes` is required
- The live collection (`oc` calls) is handled by `perfx/cluster_tool.py`, not this skill
