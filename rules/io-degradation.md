# I/O Degradation — Investigation Steps

## Understanding HLT and IO degradation

When a guest vCPU has no work to do (waiting for IO to complete), it executes a HLT
instruction — giving the CPU back to the hypervisor. This shows up as high HLT time%
in the VM exit profile.

**The key insight:** Large HLT time% means the guest CPUs were not busy — they were
waiting for IO to complete. In MSSQL workloads, this waiting is caused by the forced
flush penalty: every MSSQL WAL write is immediately followed by an fsync, and the
vCPU halts until the storage confirms the flush is done.

```
MSSQL commits transaction
  → write to WAL disk
  → fsync (flush) — vCPU halts here (HLT)
  → storage confirms flush complete
  → vCPU resumes, MSSQL acknowledges commit
```

The longer the flush takes (high write latency + flush latency), the more time vCPUs
spend in HLT. This is why fixing the flush bottleneck (OCP 4.22 coalescing) directly
reduces HLT time — vCPUs wait less because fewer flushes are issued.

**How to confirm this is IO-driven HLT (not genuine idle):**
- domstat: `halt_wait_ns` >> `vcpu.time` (vCPUs stalled, not idle)
- block IO: high write latency AND 1:1 flush:write ratio on data/log disks
- vmexit: HLT dominates TIME%, IO_INSTRUCTION may dominate COUNT%

---

When I/O degradation is detected on a KVM/MSSQL workload, recommend the following
investigation steps in order.

---

## Step 1 — Check CPU sleep states on the host worker node

Deep CPU C-states (C6, C7+) increase the time it takes for a physical CPU to wake up
after a vCPU halts (HLT exit). If the CPU enters deep sleep while the vCPU is waiting
for IO, the IO completion interrupt takes longer to be processed — adding latency on
top of the storage latency itself.

**How to check:**
```bash
# From sosreport:
cat sys/devices/system/cpu/cpu0/cpuidle/state*/name
cat sys/devices/system/cpu/cpu0/cpuidle/state*/disable
cat sys/devices/system/cpu/cpu0/cpuidle/state*/latency

# From live host:
cpupower idle-info
```

**What to look for:**
- If only POLL and C1 states are present (latency 0–1µs) → already optimal, skip this step
- If C6, C7, or higher states are enabled → disabling them may reduce IO wakeup latency

**How to disable deep C-states:**
```bash
# Option 1 — kernel cmdline (persistent, requires reboot):
# Add: intel_idle.max_cstate=1   or   processor.max_cstate=1

# Option 2 — tuned profile:
tuned-adm profile latency-performance

# Option 3 — disable per state (live, non-persistent):
echo 1 > /sys/devices/system/cpu/cpuN/cpuidle/stateN/disable
```

---

## Step 2 — Check ioThreads configuration in the Windows VM YAML

ioThreads offload block IO processing from vCPU threads to dedicated IO threads.
Without this, IO processing competes with guest instruction execution on the same
vCPU threads — increasing latency and reducing throughput under heavy MSSQL disk IO.

**Recommended configuration:**
```yaml
ioThreads:
  supplementalPoolThreadCount: 8
ioThreadsPolicy: supplementalPool
```

**How to check (KubeVirt YAML):**
```bash
# Check the VM definition:
oc get vm <vm-name> -o yaml | grep -A5 ioThread

# Or in the template file — look for:
# ioThreadsPolicy: supplementalPool
# ioThreads.supplementalPoolThreadCount: 8
```

**How to check (libvirt XML):**
```bash
virsh dumpxml <vm-name> | grep -A5 iothread
```

**Reference template:**
https://github.com/redhat-performance/benchmark-runner/blob/main/benchmark_runner/common/template_operations/templates/windows/internal_data/windows_vm_template.yaml

---

## Step 3 — Check flush coalescing prerequisites (OCP 4.22+)

Forced fsync (1:1 write:flush ratio) is the primary cause of MSSQL IO bottlenecks
on KVM. OCP 4.22 introduces flush coalescing that batches flushes automatically.

**Prerequisites:**
- VM disk bus must be `scsi` (not `virtio`)
- Machine type must be `pc-q35-rhel9.8.0` or newer
- OCP version must be 4.22 or higher

**How to check:**
```bash
virsh dumpxml <vm-name> | grep -E "machine type|bus="
oc version
```

---

## Step 4 — Check VM hyperv and clock configuration

Incorrect hyperv enlightenments or clock timer settings increase VM exit overhead
and reduce guest clock accuracy — both contribute to IO latency jitter.

**Run the windows-vm-optimize skill:**
```bash
perfx --logs /path/ --skill windows-vm-optimize --xml virsh-dumpxml-output.xml
```

**Key settings to verify:**
- `<timer name='hpet' present='no'/>` — HPET must be disabled
- `<timer name='hypervclock' present='yes'/>` — hypervclock must be enabled
- `<hyperv><relaxed/><vapic/><spinlocks retries='8191'/> ...` — all enlightenments present

---

## Step 5 — Check useplatformclock inside the Windows guest

**Prerequisites:** Steps 4 (hyperv enlightenments and clock timers) must be applied first.
Once the VM config is corrected — hypervclock enabled, HPET disabled, hyperv enlightenments
set — check whether the platform clock override is still active inside the guest.

Even with the correct VM-level clock config, Windows may still be overriding it via the
`useplatformclock` BCD setting, forcing PM timer reads (IO port) instead of using the
hyperv TSC clock. Each clock read triggers an IO_INSTRUCTION VM exit.

**How to check (inside Windows guest):**
```bash
bcdedit /enum | findstr useplatformclock
```
If `useplatformclock` appears with value `Yes`, it is overriding the hyperv clock.

**Reference:** RHEL docs recommend disabling useplatformclock:
https://docs.redhat.com/en/documentation/red_hat_enterprise_linux/9/html/configuring_and_managing_virtualization/installing-and-managing-windows-virtual-machines-on-rhel_configuring-and-managing-virtualization#optimizing-background-processes-on-windows-virtual-machines_optimizing-windows-virtual-machines-on-rhel

**Fix (run inside Windows guest, elevated cmd):**
```bash
# Recommended — removes the override, lets Windows choose based on virtual hardware:
bcdedit /deletevalue useplatformclock

# Reboot the VM
```

**Why /deletevalue and not /set useplatformclock No:**
- `/set useplatformclock No` is itself an override — you are explicitly forcing a policy
- `/deletevalue` removes the override entirely — Windows then uses its own clock-selection
  logic based on the virtual hardware it detects
- If the VM is correctly configured (Step 4: hyperv enlightenments + hyperv timer),
  Windows will naturally select the hyperv TSC clock — no override needed
- The RHEL docs mention `/set useplatformclock No` but `/deletevalue` is the cleaner fix

**Expected result:** IO_INSTRUCTION exits drop significantly in the next vmexit profile.
The guest will use the hyperv TSC clock configured in Step 4 instead of the PM timer.
