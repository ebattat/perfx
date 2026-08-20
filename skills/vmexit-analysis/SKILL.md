# vmexit-analysis

Analyze KVM VM-EXIT profile to detect platform clock issues, IO-bound vCPUs,
and excessive exit overhead. Detects the useplatformclock issue causing IO_INSTRUCTION exits.

## Usage

/vmexit-analysis --file <kvm_vmexit_stats_file> [--vcpus N] [--duration S]

## Inputs

- `file` (required): kvm_vmexit_stats output file (from `perf kvm stat report`)
- `--vcpus` (optional): number of vCPUs to compute exit time as % of available CPU time
- `--duration` (optional): collection window in seconds (default 60)

## Key Knowledge — VM Exit Analysis

### HLT vs IO_INSTRUCTION — COUNT vs TIME

Always analyze both COUNT% and TIME% separately — they tell different stories:
- HLT high TIME% = guest stalled waiting on IO (long duration per exit)
- IO_INSTRUCTION high COUNT% + low avg_us = rapid clock reads (not storage IO)

Example: IO_INSTRUCTION 68% count / 13% time = many fast exits (clock reads).
HLT 26% count / 86% time = few but long exits (stalled on storage).
TIME% shows impact. COUNT% shows frequency.

### HLT is not always a problem

HLT alone does NOT indicate a problem — a genuinely idle guest also shows high HLT time%.
To confirm IO-driven HLT (not genuine idle):
- domstat: halt_wait_ns >> vcpu.time (vCPUs stalled)
- block IO write latency high AND 1:1 flush:write ratio

### useplatformclock detection signature

Pattern: IO_INSTRUCTION high COUNT% + low avg_us (<200µs) + HLT high TIME%

Windows reads the PM timer (port 0x408) via IO port instead of using the hyperv TSC clock.
Each clock read = 1 IO_INSTRUCTION VM exit at ~50µs. Millions per minute under MSSQL load.

Fix (inside Windows guest, elevated cmd):
```
bcdedit /deletevalue useplatformclock
(reboot)
```

Why /deletevalue not /set useplatformclock No:
- /set No is itself an override (forcing a policy)
- /deletevalue removes the override — Windows chooses based on virtual hardware
- Requires Step 4 VM config (hyperv enlightenments + hyperv timer) to be applied first

Reference: https://docs.redhat.com/en/documentation/red_hat_enterprise_linux/9/html/configuring_and_managing_virtualization/installing-and-managing-windows-virtual-machines-on-rhel_configuring-and-managing-virtualization#optimizing-background-processes-on-windows-virtual-machines_optimizing-windows-virtual-machines-on-rhel

### Exit time context

penalty% = total_exit_time_s / (n_vcpus × collection_duration_s)
Example: 911s / (24 × 60s) = 63% of available vCPU time consumed by exits.

## Steps

1. Download the vmexit stats file
2. Parse all VM exit types: name, samples, samples%, time%, avg_us
3. Sort by time% descending — HLT typically dominates time%
4. Analyze HLT exits (primary — dominates exit TIME):
   - HLT high time% → guest IO-bound or idle — cross-reference with domstat
   - Large HLT time% = guest CPUs gave CPU back to host (waiting on IO/flushes)
5. Analyze IO_INSTRUCTION exits (secondary — dominates COUNT):
   - High count% + avg_us < 200µs → useplatformclock pattern (clock reads not storage IO)
6. If useplatformclock pattern detected → recommend bcdedit /deletevalue useplatformclock
   - But first verify VM config has hyperv enlightenments + hyperv timer (prerequisite)
7. If --vcpus provided: compute total_exit_time / (vcpus × duration) = % of available CPU time
8. Save report to logs/
