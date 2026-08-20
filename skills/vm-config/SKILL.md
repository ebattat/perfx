# vm-config

Audit a Windows or Linux VM YAML configuration against the recommended template
and flag missing or incorrect settings that cause performance issues.

## Usage

/vm-config --file <vm-yaml-file> [--os windows|linux]

## Inputs

- `file` (required): Path to the VM YAML file (KubeVirt VirtualMachine format)
- `--os` (optional): `windows` or `linux` — if not provided, chai-bot will detect from content

## Rules

Before auditing, read and apply these rules:

- `rules/windows-vm-template.yaml` — recommended Windows VM configuration (reference template)
- `rules/linux-vm-template.yaml` — recommended Linux VM configuration (reference template)
- `rules/io-degradation.md` — IO degradation investigation steps, especially:
  - Step 2: ioThreads configuration (supplementalPool, 8 threads)
  - Step 4: hyperv enlightenments and clock timer settings
- `methodology/vm-tuning-guide.md` — full VM tuning guide including:
  - VirtualMachineClusterPreference (always required)
  - Disk/network best practices (avoid sata, e1000e)
  - C-state tuning via Node Tuning Operator
  - Hugepages and CPU QoS

## Steps

1. Read `rules/windows-vm-template.yaml` or `rules/linux-vm-template.yaml` as the reference
2. Download the user-provided VM YAML file
3. For Windows VMs: Run `python3 /workspace/skills/vm-config/check_vm_config.py <file>`
4. For Linux VMs: Use the linux check function
5. Compare each setting against the reference template
6. Flag missing settings and explain the performance impact:
   - Missing VirtualMachineClusterPreference → critical optimizations not applied automatically
   - Missing hyperv enlightenments → higher VM exit overhead, useplatformclock issue
   - Missing clock timers (hpet, hypervclock) → PM timer IO exits
   - Missing ioThreads → IO processed on vCPU threads, higher latency
   - autoattachMemBalloon not false → MSSQL buffer pool can be shrunk
   - Machine type too old → OCP 4.22 flush coalescing unavailable
   - bus: sata or model: e1000e → poor performance, use virtio
7. Save report to logs/ and share the path with the user
8. Summarize: X issues found, Y passed, severity level
9. **After VM config is fixed** — remind the user to check useplatformclock inside the guest:
   - Even with correct hyperv/clock VM config, Windows may still override via BCD setting
   - Check: `bcdedit /enum | findstr useplatformclock`
   - If present: `bcdedit /deletevalue useplatformclock` then reboot
   - See rules/io-degradation.md Step 5 for full details
