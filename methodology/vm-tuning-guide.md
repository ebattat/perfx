# VM Configuration and Tuning Guide

Reference: https://developers.redhat.com/blog/2026/05/06/best-practice-configuration-and-tuning-linux-and-windows-vms#vm_definition
Tuning & Scaling Guide: https://access.redhat.com/articles/6994974
VirtualMachinePreference customization: https://access.redhat.com/solutions/7123335

---

## Step 1 — Apply a VirtualMachineClusterPreference

Always apply a `VirtualMachineClusterPreference` to every VM — it automatically applies
critical optimizations (hyperv enlightenments, clock config, bus type, etc.).

```bash
# List available preferences
oc get VirtualMachineClusterPreference

# Common preferences
windows.2k25.virtio   # Windows Server 2025
windows.2k22.virtio   # Windows Server 2022
rhel.9.virtio         # RHEL 9
```

Apply in the VM spec:
```yaml
spec:
  preference:
    name: windows.2k25.virtio
```

> A reboot is required if the VM is already running when preferences are applied.

Inspect what settings are active on a running VM:
```bash
oc get vmi <vm_name> -o yaml
```

---

## Step 2 — Disk configuration

| Setting | Recommended | Avoid |
|---|---|---|
| Bus type | `bus: virtio` | `bus: sata` — poor performance |
| IO threads | `ioThreadsPolicy: supplementalPool` (OCP 4.19+) | none |
| Block volumes | `io: native` applied automatically | — |
| Filesystem volumes | Use **preallocation** to enable `io: native` | — |

**io: native** bypasses the page cache and issues direct IO to the block device,
reducing latency and CPU overhead. For filesystem-backed PVCs, preallocation
must be enabled at PVC creation time to unlock this mode.

**ioThreads supplementalPool** (introduced OCP 4.19):
Reference: https://developers.redhat.com/blog/2025/06/23/feature-introduction-multiple-iothreads-openshift-virtualization
- Spreads VM disk IO across multiple submission threads mapped to multiple disk queues
- Requires `blockMultiQueue: true` and `bus: virtio`
- Recommended: 16 vCPUs + 4 IOthreads as a starting point; up to 8-16 on fast storage
- Up to 2× improvement in microbenchmarks
- Thread count adds to vCPU count for CPU request calculations
- Not compatible with `dedicatedCpuPlacement` or `isolateEmulatorThread`
- Storage live migration unsupported before 4.21

---

## Step 3 — Network configuration

| Setting | Recommended | Avoid |
|---|---|---|
| Model | `model: virtio` | `model: e1000e` — poor performance |
| Throughput | `networkInterfaceMultiqueue: true` | — |

---

## Step 4 — Host Tuned profile

OpenShift nodes default to a **"throughput performance"** Tuned profile, suitable
for broad workload types. This is managed via the Node Tuning Operator.

For latency-sensitive workloads (MSSQL, real-time), additional profiles are available.
Check the active profile on a node:
```bash
tuned-adm active
```

---

## Step 5 — Host C-state tuning (latency-sensitive workloads)

For MSSQL and other latency-sensitive workloads, limit CPU sleep depth to C1.
The OCP-native way (no reboot required) is via the Node Tuning Operator:

```yaml
apiVersion: tuned.openshift.io/v1
kind: Tuned
metadata:
  name: c1-lowlatency
  namespace: openshift-cluster-node-tuning-operator
spec:
  profile:
  - data: |
      [main]
      summary=Pins to C1 cstate for low latency
      include=openshift-node
      [cpu]
      force_latency=1
    name: c1-lowlatency
  recommend:
  - machineConfigLabels:
      machineconfiguration.openshift.io/role: "worker"
    priority: 20
    profile: c1-lowlatency
```

Verify C-states after applying:
```bash
# From sosreport or live host:
cat /sys/devices/system/cpu/cpu0/cpuidle/state*/name
cat /sys/devices/system/cpu/cpu0/cpuidle/state*/latency
# Expected: only POLL (0us) and C1 (1us)
```

---

## Step 6 — Hugepages (for workloads with large memory footprint)

Default RHEL kernels use THP (Transparent HugePages) with auto-promotion.
For workloads sensitive to TLB misses (large MSSQL buffer pools):

```yaml
# In VM spec:
domain:
  memory:
    hugepages:
      pageSize: 1Gi   # 1GB hugepages
```

Pre-allocate on the node via MachineConfig or Node Tuning Operator.

---

## Step 7 — CPU isolation and pinning

For workloads sensitive to scheduler disruptions or requiring very low latency
(e.g. MSSQL on large VMs):

- Pin vCPUs to dedicated physical CPUs to prevent scheduler interference
- Isolate CPUs from the host OS scheduler using `isolcpus` or CPU Manager
- Use `dedicatedCpuPlacement: true` in the VM spec

```yaml
spec:
  domain:
    cpu:
      dedicatedCpuPlacement: true
```

See: https://access.redhat.com/articles/6994974 — Pinning sections for full details.

---

## Step 8 — CPU Allocation Ratio

Default overcommit is 10:1. For latency-sensitive MSSQL workloads, reduce or
set exact CPU requests/limits to guarantee CPU resources:

```yaml
resources:
  requests:
    cpu: "24"
  limits:
    cpu: "24"    # requests == limits = guaranteed QoS
```
