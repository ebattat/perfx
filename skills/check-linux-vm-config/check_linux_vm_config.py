#!/usr/bin/env python3
"""
Check Linux VM YAML configuration against rules/linux-vm-checks.yaml.
Usage: python3 check_linux_vm_config.py <customer-vm.yaml>
"""
import sys
import re
from datetime import datetime
from pathlib import Path

try:
    import yaml
except ImportError:
    print("ERROR: pyyaml not installed. Run: pip install pyyaml", file=sys.stderr)
    sys.exit(1)


RULES_DIR   = Path(__file__).parent.parent.parent / "rules"
LOGS_DIR    = Path(__file__).parent.parent.parent / "logs"
CHECKS_FILE = RULES_DIR / "linux-vm-checks.yaml"


def _load(path):
    with open(path) as f:
        raw = f.read()
    raw = re.sub(r'\{%-?.*?-?%\}', '', raw)
    raw = re.sub(r'\{\{.*?\}\}', '"__template__"', raw)
    return yaml.safe_load(raw)


def _domain(doc):
    return (doc.get("spec", {})
               .get("template", {})
               .get("spec", {})
               .get("domain", {}))


def _load_checks():
    if not CHECKS_FILE.exists():
        print(f"ERROR: rules file not found: {CHECKS_FILE}", file=sys.stderr)
        sys.exit(1)
    return yaml.safe_load(CHECKS_FILE.read_text())


def check(vm_path):
    doc     = _load(vm_path)
    domain  = _domain(doc)
    vm_name = doc.get("metadata", {}).get("name", Path(vm_path).stem)
    checks  = _load_checks()

    findings = []
    passes   = []

    devices   = domain.get("devices") or {}
    cpu       = domain.get("cpu") or {}
    io_policy = domain.get("ioThreadsPolicy")
    io_count  = (domain.get("ioThreads") or {}).get("supplementalPoolThreadCount")
    disks     = devices.get("disks") or []
    interfaces = devices.get("interfaces") or []

    def _fail(section, key, detail):
        findings.append(("FAIL", section, key, detail))

    def _warn(section, key, detail):
        findings.append(("WARN", section, key, detail))

    def _ok(section, key):
        passes.append((section, key))

    dev_rules = checks.get("devices", {})

    # blockMultiQueue
    bmq = devices.get("blockMultiQueue")
    exp = dev_rules.get("blockMultiQueue")
    if exp is not None:
        if bmq != exp:
            _fail("devices", "blockMultiQueue", f"={bmq!r} (want {exp!r})")
        else:
            _ok("devices", "blockMultiQueue")

    # networkInterfaceMultiqueue
    net_mq = devices.get("networkInterfaceMultiqueue")
    exp = dev_rules.get("networkInterfaceMultiqueue")
    if exp is not None:
        if net_mq != exp:
            _fail("devices", "networkInterfaceMultiqueue", f"={net_mq!r} (want {exp!r})")
        else:
            _ok("devices", "networkInterfaceMultiqueue")

    # NIC model
    nic_models = {iface.get("model", "virtio") for iface in interfaces}
    bad_nics = nic_models & {"e1000", "e1000e", "rtl8139"}
    if bad_nics:
        _fail("devices", "NIC model", f"non-virtio NIC ({', '.join(sorted(bad_nics))}) — switch to model: virtio")
    else:
        _ok("devices", "NIC model")

    # disk bus and cache (all disks for bus, root disk only for cache)
    bus_issues = []
    cache_missing = False
    for disk in disks:
        bus = (disk.get("disk") or {}).get("bus", "")
        cache = (disk.get("disk") or {}).get("cache", "")
        if bus and bus != "virtio":
            bus_issues.append(f"{disk.get('name','?')}: bus={bus!r}")
        if disk.get("bootOrder") == 1:
            if cache != "none":
                cache_missing = True

    if bus_issues:
        _fail("devices", "disk bus", f"non-virtio bus: {', '.join(bus_issues)}")
    else:
        _ok("devices", "disk bus")

    if cache_missing:
        _fail("devices", "disk cache", "root disk cache not set to 'none' — risk of buffered IO after live migration")
    else:
        _ok("devices", "disk cache")

    # ioThreadsPolicy
    if io_policy != "supplementalPool":
        _fail("ioThreads", "ioThreadsPolicy", f"={io_policy!r} (want 'supplementalPool')")
    else:
        _ok("ioThreads", "ioThreadsPolicy")

    # ioThreads count
    def _to_int(v, default=1):
        try:
            return int(v)
        except (TypeError, ValueError):
            return default
    vcpus = _to_int(cpu.get("cores", 1), 1) * _to_int(cpu.get("sockets", 1), 1)
    rec_threads = max(4, min(vcpus // 4, 16)) if vcpus > 1 else 4
    if not io_count:
        _fail("ioThreads", "supplementalPoolThreadCount", f"not set (want ≥{rec_threads} based on {vcpus} vCPUs)")
    else:
        _ok("ioThreads", "supplementalPoolThreadCount")

    # ── output ────────────────────────────────────────────────────────────────
    lines = []
    lines.append("=" * 65)
    lines.append("LINUX VM CONFIGURATION AUDIT")
    lines.append("=" * 65)
    lines.append(f"\nVM        : {vm_name}")
    lines.append(f"File      : {vm_path}")
    lines.append(f"Reference : {CHECKS_FILE}")
    fails = sum(1 for s, *_ in findings if s == "FAIL")
    warns = sum(1 for s, *_ in findings if s == "WARN")
    lines.append(f"\nResult    : {fails} critical issue(s), {warns} warning(s), {len(passes)} check(s) passed\n")

    lines.append(f"  {'Setting':<28} {'Customer VM':<45} {'Recommended':<50} Status")
    lines.append(f"  {'─'*28} {'─'*45} {'─'*50} {'─'*40}")

    def row(setting, customer, recommended, status):
        lines.append(f"  {setting:<28} {customer:<45} {recommended:<50} {status}")

    # disk bus
    bus_vals = list({(d.get("disk") or {}).get("bus", "?") for d in disks})
    bus_str = ", ".join(bus_vals) if bus_vals else "not set"
    row("disk bus", bus_str, "virtio",
        "✅ OK" if not bus_issues else "❌ WRONG BUS")

    # disk cache (root disk)
    root_cache = next(((d.get("disk") or {}).get("cache", "not set")
                       for d in disks if d.get("bootOrder") == 1), "not set")
    row("disk cache (root)", root_cache, "none",
        "✅ OK" if root_cache == "none" else "⚠️ NOT SET — risk of buffered IO after live migration")

    # blockMultiQueue
    row("blockMultiQueue", str(bmq).lower() if bmq is not None else "not set", "true",
        "✅ OK" if bmq is True else "❌ MISSING")

    # networkInterfaceMultiqueue
    row("networkInterfaceMultiqueue", str(net_mq).lower() if net_mq is not None else "not set", "true",
        "✅ OK" if net_mq is True else "❌ MISSING")

    # NIC model
    nic_str = ", ".join(sorted(nic_models)) if nic_models else "virtio (default)"
    row("NIC model", nic_str, "virtio",
        "❌ WRONG MODEL" if bad_nics else "✅ OK")

    # ioThreads
    rec_io_str = f"≥{rec_threads} (based on {vcpus} vCPUs)"
    row("ioThreads", str(io_count) if io_count else "None", rec_io_str,
        "✅ OK" if io_count else "❌ MISSING (requires OCP 4.19+)")
    row("ioThreadsPolicy", str(io_policy) if io_policy else "None", "supplementalPool",
        "✅ OK" if io_policy == "supplementalPool" else "❌ MISSING (requires OCP 4.19+)")

    lines.append("")
    lines.append("─" * 65)
    lines.append("RECOMMENDATION")
    lines.append("─" * 65)
    if any(s == "FAIL" for s, *_ in findings):
        lines.append(f"  Reference: {CHECKS_FILE.relative_to(CHECKS_FILE.parent.parent)}")
        lines.append("")
        lines.append(f"  {'Setting':<35} {'Issue'}")
        lines.append(f"  {'─'*35} {'─'*40}")
        for sev, section, key, detail in findings:
            if sev == "FAIL":
                lines.append(f"  {section+'.'+key:<35} {detail}")
    else:
        lines.append("  Configuration matches recommended template.")

    return "\n".join(lines)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Check Linux VM configuration against best practices")
    parser.add_argument("vm_yaml", help="Path to VM YAML file")
    args = parser.parse_args()

    report = check(args.vm_yaml)
    print(report)

    LOGS_DIR.mkdir(exist_ok=True)
    ts   = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    name = Path(args.vm_yaml).stem
    out  = LOGS_DIR / f"linux_vm_config_audit_{name}_{ts}.log"
    out.write_text(report)
    print(f"\nReport saved to: {out}")


if __name__ == "__main__":
    main()
