# memory-analysis

Analyze guest memory pressure from virsh domstats balloon fields.
Detects swap activity, major page faults, and RSS near maximum.

## Usage

/memory-analysis --file <domstat_file>

## Inputs

- `file` (required): virsh domstats output file

## Rules

Before analyzing, read and apply these rules:

- `rules/io-degradation.md` — memory pressure compounds IO bottlenecks (swap competes on same storage)

## Steps

1. Read `rules/io-degradation.md` to understand how memory pressure compounds IO issues
2. Download the domstat file
3. Compute deltas for balloon fields:
   - balloon.rss, balloon.maximum → utilization %
   - balloon.swap_in, balloon.swap_out → swap rate (KB/s over window)
   - balloon.major_fault → page faults requiring disk IO (expensive)
   - balloon.minor_fault → page faults resolved from RAM (cheap)
   - balloon.unused → free memory trend
4. Flag when RSS approaches maximum (near OOM)
5. Flag any swap_in delta > 0 (guest pulling pages from disk)
6. Flag major fault rate — compare against reference (healthy = near zero)
7. Note: swap IO competes with MSSQL on the same storage backend
8. Recommend increasing VM memory if swap is present
9. Check SQL Server max memory setting guidance
10. Save report to logs/
