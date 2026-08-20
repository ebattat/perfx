# delta-analysis

Analyze virsh domstats output across CPU, memory, block IO, and vCPU stall metrics.
Use this first to get a full picture and determine which targeted skill to run next.

## Usage

/delta-analysis --file <domstat_file>

## Inputs

- `file` (required): virsh domstats output file

## Rules

Before analyzing, read and apply these rules:

- `rules/io-degradation.md` — use findings to guide which targeted skills to run next

## Steps

1. Read `rules/io-degradation.md` to understand what to look for
2. Download the domstat file
3. Parse all key fields:
   - CPU: cpu.time, cpu.user, cpu.system, cpu.haltpoll.*
   - Memory: balloon.rss, balloon.unused, balloon.swap_in, balloon.swap_out, balloon.major_fault
   - Block IO: block.N.wr.reqs/times, rd.reqs/times, fl.reqs/times for all N
   - vCPU: vcpu.N.time, vcpu.N.halt_wait_ns.sum, vcpu.N.io_exits.sum for all N
   - Network: net.N.rx/tx bytes, pkts, drops, errs
4. Flag anomalies: swap_in > 0, high halt_wait vs vcpu.time, high write latency
5. Based on findings, recommend which targeted skill to run next:
   - IO bottleneck → run /io-analysis
   - Memory pressure → run /memory-analysis
   - VM exit issues → run /vmexit-analysis
6. Save report to logs/
