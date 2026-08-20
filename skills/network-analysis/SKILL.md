# network-analysis

Analyze guest network throughput, packet drops, errors, and packet rates from virsh domstats.

## Usage

/network-analysis --file <domstat_file>

## Inputs

- `file` (required): virsh domstats output file

## Rules

No specific rules file yet. Apply general network analysis principles:
- Any packet drops indicate a bottleneck (RX drops = guest-side, TX drops = host-side)
- High pps can saturate vhost even when bandwidth looks acceptable
- For MSSQL: TX >> RX is normal; RX >> TX suggests bulk ingest

## Steps

1. Download the domstat file
2. Parse net.N.* fields for all interfaces
3. Compute deltas: rx/tx bytes, pkts, drops, errs
4. Calculate:
   - Throughput: bytes_delta × 8 / duration / 1024² = Mbps
   - Packet rate: pkts_delta / duration = pps
   - Average packet size: bytes_delta / pkts_delta
5. Distinguish RX drops (guest CPU can't drain vNIC) from TX drops (host NIC saturated)
6. Flag high pps — can saturate vhost interrupt even at low bandwidth
7. Flag small average packet size — many tiny TDS frames for MSSQL
8. Flag TX/RX ratio: RX >> TX is unusual for MSSQL query workloads
9. Save report to logs/
