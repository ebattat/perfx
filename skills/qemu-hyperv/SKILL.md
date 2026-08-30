# /qemu-hyperv

**Windows VMs only.** Verify that hyperv enlightenments are actually applied to the running QEMU process on an OCP node. Linux VMs do not use hyperv enlightenments and will be skipped.

Complements `/vm-config` — while `/vm-config` checks the VM YAML spec, this skill checks
the **running QEMU process** to confirm the config was applied end-to-end.

## Steps

1. Run the check against a specific node:
   ```bash
   python3 skills/qemu-hyperv/check_qemu_hyperv.py --node <node-name>
   ```

   Or check all worker nodes:
   ```bash
   python3 skills/qemu-hyperv/check_qemu_hyperv.py --all
   ```

2. Report findings to the user

## Requirements

- `oc` CLI logged into the cluster
- A Windows VM must be running on the target node

## Output Sections

- SEVERITY: PASS / FAIL / UNKNOWN
- FINDINGS: ✅/❌ for each expected hv- flag
- RECOMMENDATION: what to fix if flags are missing
- SUMMARY: X/14 flags present

## Notes

- UNKNOWN means no QEMU process was found (no Windows VM running on that node)
- `hv-spinlocks=0x1fff` means spinlocks=8191 — correct value per the Windows VM template
