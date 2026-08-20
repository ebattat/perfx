# io-analysis

Analyze block IO latency and vCPU stall patterns from virsh domstats output.
Detects forced fsync (1:1 flush:write), write latency, flush time %, and IO-bound vCPUs.

## Usage

/io-analysis --file <domstat_file>

## Inputs

- `file` (required): virsh domstats output file

## Key Knowledge — IO Degradation on KVM/MSSQL

### Understanding HLT and IO degradation

When a guest vCPU has no work to do (waiting for IO to complete), it executes a HLT
instruction — giving the CPU back to the hypervisor. Large HLT time% means the guest
CPUs were not busy — they were waiting for IO to complete.

In MSSQL workloads this waiting is caused by forced flush:
```
MSSQL commits → write to WAL disk → fsync (flush) → vCPU halts (HLT)
→ storage confirms flush → vCPU resumes → MSSQL acknowledges commit
```

Confirm IO-driven HLT (not genuine idle):
- domstat: halt_wait_ns >> vcpu.time
- block IO: high write latency AND 1:1 flush:write ratio on data/log disks
- vmexit: HLT dominates TIME%, IO_INSTRUCTION may dominate COUNT%

### Flush analysis rules

- 1:1 flush:write ratio = forced fsync (strongest signal) — MSSQL WAL pattern
- Also check flush time %: flush_total_ms / (write_total_ms + flush_total_ms) × 100
- High flush time % is significant even without 1:1 ratio
- total_commit_latency = write_avg_ms + flush_avg_ms (what MSSQL pays per commit)

### Investigation steps when IO degradation is detected

**Step 1 — Check CPU sleep states on host:**
- Deep C-states (C6, C7+) increase CPU wakeup latency after HLT exit
- Check: `cat sys/devices/system/cpu/cpu0/cpuidle/state*/name` from sosreport
- If only POLL and C1 → already optimal
- If C6/C7 enabled → disable with: `tuned-adm profile latency-performance`

**Step 2 — Check ioThreads in VM YAML:**
- ioThreads offload IO from vCPU threads to dedicated IO threads
- Required: `ioThreadsPolicy: supplementalPool` + `supplementalPoolThreadCount: 8`
- Check: `oc get vm <vm-name> -o yaml | grep -A5 ioThread`

**Step 3 — Check flush coalescing (OCP 4.22+):**
- Forced fsync is the primary MSSQL IO bottleneck
- Fix requires: bus=scsi + machine type pc-q35-rhel9.8.0 + OCP 4.22+
- For older OCP/virtio: CNV-50763 cache mode workaround

**Step 4 — Check VM hyperv and clock configuration:**
- HPET must be disabled: `hpet: present: false`
- hypervclock must be enabled: `hyperv: {}`
- All hyperv enlightenments must be present (relaxed, vapic, synic, spinlocks:8191, etc.)
- Reference: rules/windows-vm-template.yaml

**Step 5 — Check useplatformclock inside Windows guest:**
- Prerequisites: Step 4 VM config must be applied first
- Check: `bcdedit /enum | findstr useplatformclock`
- If present: `bcdedit /deletevalue useplatformclock` then reboot
- Why /deletevalue not /set No: removes override, lets Windows choose based on virtual hardware
- Reference: https://docs.redhat.com/en/documentation/red_hat_enterprise_linux/9/html/configuring_and_managing_virtualization/installing-and-managing-windows-virtual-machines-on-rhel_configuring-and-managing-virtualization#optimizing-background-processes-on-windows-virtual-machines_optimizing-windows-virtual-machines-on-rhel

## Steps

1. Download the domstat file
2. Parse all block.N.wr.reqs, wr.times, fl.reqs, fl.times fields
3. For each block device compute:
   - write avg latency = wr.times_delta / wr.reqs_delta / 1,000,000 ms
   - flush avg latency = fl.times_delta / fl.reqs_delta / 1,000,000 ms
   - flush:write ratio = fl.reqs_delta / wr.reqs_delta
   - flush time % = fl_total_ms / (wr_total_ms + fl_total_ms) × 100
4. Show flush summary table across all block devices
5. Flag 1:1 flush:write ratio — forced fsync, strongest IO bottleneck signal
6. Flag high flush time % even without 1:1 ratio
7. Compute vCPU idle% = halt_wait_ns_delta / (halt_wait_ns_delta + vcpu.time_delta)
8. Apply Investigation Steps 1-5 above based on findings
9. Save report to logs/
