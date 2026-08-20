# cpu-analysis

Analyze CPU utilization of a qemu-kvm process from pidstat output.
Identifies total CPU load, KVM exit overhead, guest execution time, and host contention.

## Usage

/cpu-analysis --file <pidstat_file>

## Inputs

- `file` (required): pidstat output file captured with `pidstat -t -p <qemu-pid>`

## Rules

Before analyzing, read and apply these rules:

- `rules/io-degradation.md` — Step 1: CPU sleep states on the host worker node

## Steps

1. Read `rules/io-degradation.md` Step 1 for CPU sleep state guidance
2. Download the pidstat file
3. Find the main qemu-kvm process line (tgid != '-' and tid == '-')
4. IMPORTANT: %CPU is the SUM across ALL vCPUs — divide by vCPU count for per-vCPU utilization
5. Parse vCPU threads (lines containing 'CPU N/KVM'):
   - If all vCPU threads show near-zero %CPU → guest is IO-bound, NOT idle
   - Do NOT recommend adding vCPUs when this pattern is seen
6. Check %system: elevated %system reflects VM exit frequency/type, NOT emulated IO overhead
   - Cross-reference with vmexit-analysis to identify which exit types dominate
7. Check %wait: > 0 indicates host CPU contention
8. Parse IO threads (iothread) — should show near-zero CPU
9. Recommend checking CPU sleep states from rules/io-degradation.md Step 1 if IO latency is high
10. Save report to logs/
