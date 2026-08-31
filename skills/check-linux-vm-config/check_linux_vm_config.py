#!/usr/bin/env python3
"""
Check Linux VM YAML configuration against rules/linux-vm-checks.yaml.
Usage: python3 check_linux_vm_config.py <customer-vm.yaml>
"""
import os
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
LOGS_DIR    = Path(os.environ.get("PERFX_LOGS_DIR", Path(__file__).parent.parent.parent / "logs"))
CHECKS_FILE = RULES_DIR / "linux-vm-checks.yaml"


def _load(path):
    with open(path) as f:
        raw = f.read()
    raw = re.sub(r'\{%-?.*?-?%\}', '', raw)
    raw = re.sub(r'\{\{.*?\}\}', '"__template__"', raw)
    # handle multi-document YAML — find the VirtualMachine document
    docs = list(yaml.safe_load_all(raw))
    docs = [d for d in docs if d]  # filter None (empty docs)
    for doc in docs:
        if doc.get("kind") == "VirtualMachine":
            return doc
    return docs[0] if docs else {}


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


def _to_int(v, default=1):
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def _generate_corrected_yaml(vm_path, findings):
    """Generate corrected VM YAML with Linux best-practice fixes applied."""
    import yaml as _yaml
    doc     = _load(vm_path)
    domain  = _domain(doc)
    checks  = _load_checks()
    changes = []

    actionable = {(section, key) for sev, section, key, _ in findings}

    # ioThreads
    cpu    = domain.get("cpu") or {}
    vcpus  = _to_int(cpu.get("cores", 1), 1) * _to_int(cpu.get("sockets", 1), 1)
    rec_threads = max(4, min(vcpus // 4, 16)) if vcpus > 1 else 4
    if ("ioThreads", "ioThreadsPolicy") in actionable or ("ioThreads", "supplementalPoolThreadCount") in actionable:
        domain["ioThreadsPolicy"] = "supplementalPool"
        domain["ioThreads"] = {"supplementalPoolThreadCount": rec_threads}
        changes.append("ioThreads")

    # devices
    devices = domain.setdefault("devices", {})
    if ("devices", "blockMultiQueue") in actionable:
        devices["blockMultiQueue"] = True
        changes.append("blockMultiQueue")
    if ("devices", "networkInterfaceMultiqueue") in actionable:
        devices["networkInterfaceMultiqueue"] = True
        changes.append("networkInterfaceMultiqueue")

    # evictionStrategy (fix for both FAIL and WARN)
    spec = (doc.get("spec") or {}).get("template", {}).setdefault("spec", {})
    if ("spec", "evictionStrategy") in actionable:
        spec["evictionStrategy"] = "LiveMigrate"
        changes.append("evictionStrategy")

    # clean kubernetes metadata
    meta = doc.get("metadata", {})
    for field in ["managedFields", "resourceVersion", "uid", "creationTimestamp",
                  "generation", "finalizers", "annotations"]:
        meta.pop(field, None)
    doc.pop("status", None)

    raw = _yaml.dump(doc, default_flow_style=False, sort_keys=False).rstrip()

    comments = {}
    if "ioThreads" in changes:
        comments["ioThreadsPolicy: supplementalPool"] = "# ADDED: offloads IO from vCPU threads"
        comments["supplementalPoolThreadCount:"] = f"# ADDED: {rec_threads} threads for {vcpus} vCPUs"
    if "blockMultiQueue" in changes:
        comments["blockMultiQueue: true"] = "# ADDED: enables multi-queue for block devices"
    if "networkInterfaceMultiqueue" in changes:
        comments["networkInterfaceMultiqueue: true"] = "# ADDED: enables multi-queue for network"
    if "evictionStrategy" in changes:
        comments["evictionStrategy: LiveMigrate"] = "# ADDED: live migrate on node drain"

    annotated = []
    for line in raw.splitlines():
        stripped = line.strip()
        comment = next((v for k, v in comments.items()
                        if stripped == k or stripped.startswith(k + " ") or stripped.startswith(k + ":")), None)
        if comment and not stripped.startswith("#"):
            line = f"{line}  {comment}"
        annotated.append(line)

    out = [f"# Corrected YAML — changes applied: {', '.join(changes)}"]
    out.append("# Review before applying: oc apply -f <this-file>")
    out.append("")
    out.extend(annotated)
    return "\n".join(out)


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
    for disk in disks:
        bus = (disk.get("disk") or {}).get("bus", "")
        if bus and bus != "virtio":
            bus_issues.append(f"{disk.get('name','?')}: bus={bus!r}")

    if bus_issues:
        _fail("devices", "disk bus", f"non-virtio bus: {', '.join(bus_issues)}")
    else:
        _ok("devices", "disk bus")

    # ioThreadsPolicy
    if io_policy != "supplementalPool":
        _fail("ioThreads", "ioThreadsPolicy", f"={io_policy!r} (want 'supplementalPool')")
    else:
        _ok("ioThreads", "ioThreadsPolicy")

    # ioThreads count
    vcpus = _to_int(cpu.get("cores", 1), 1) * _to_int(cpu.get("sockets", 1), 1)
    rec_threads = max(4, min(vcpus // 4, 16)) if vcpus > 1 else 4
    if not io_count:
        _fail("ioThreads", "supplementalPoolThreadCount", f"not set (want ≥{rec_threads} based on {vcpus} vCPUs)")
    else:
        _ok("ioThreads", "supplementalPoolThreadCount")

    # ── cpu topology ─────────────────────────────────────────────────────────
    cpu_rules = checks.get("cpu", {})
    if cpu_rules:
        sockets = cpu.get("sockets", 1)
        try:
            sockets = int(sockets)
        except (TypeError, ValueError):
            sockets = 1
        if sockets > 1:
            _warn("cpu", "sockets", f"sockets={sockets} — use cores instead; set sockets: 1, threads: 1")
        else:
            _ok("cpu", "sockets")

    # ── evictionStrategy (optional) ──────────────────────────────────────────
    spec = (doc.get("spec") or {}).get("template", {}).get("spec", {})
    eviction = spec.get("evictionStrategy")
    if checks.get("evictionStrategy") == "LiveMigrate":
        if eviction != "LiveMigrate":
            _warn("spec", "evictionStrategy", f"={eviction!r} — set to 'LiveMigrate' to avoid shutdown on node drain")
        else:
            _ok("spec", "evictionStrategy")

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

    # disk bus (only if in rules)
    if dev_rules.get("disk", {}).get("bus") or dev_rules.get("disk", {}).get("root_bus"):
        bus_vals = list({(d.get("disk") or {}).get("bus", "") for d in disks if (d.get("disk") or {}).get("bus")})
        bus_str = ", ".join(sorted(bus_vals)) if bus_vals else "not set"
        row("disk bus", bus_str, "virtio",
            "✅ OK" if not bus_issues else "❌ WRONG BUS")

    # blockMultiQueue (only if in rules)
    if dev_rules.get("blockMultiQueue") is not None:
        row("blockMultiQueue", str(bmq).lower() if bmq is not None else "not set", "true",
            "✅ OK" if bmq is True else "❌ MISSING")

    # networkInterfaceMultiqueue (only if in rules)
    if dev_rules.get("networkInterfaceMultiqueue") is not None:
        row("networkInterfaceMultiqueue", str(net_mq).lower() if net_mq is not None else "not set", "true",
            "✅ OK" if net_mq is True else "❌ MISSING")

    # NIC model (only if in rules)
    if dev_rules.get("NIC", {}).get("model") == "virtio":
        nic_str = ", ".join(sorted(nic_models)) if nic_models else "virtio (default)"
        row("NIC model", nic_str, "virtio",
            "❌ WRONG MODEL" if bad_nics else "✅ OK")

    # ioThreads
    rec_io_str = f"≥{rec_threads} (based on {vcpus} vCPUs)"
    row("ioThreads", str(io_count) if io_count else "None", rec_io_str,
        "✅ OK" if io_count else "❌ MISSING (requires OCP 4.19+)")
    row("ioThreadsPolicy", str(io_policy) if io_policy else "None", "supplementalPool",
        "✅ OK" if io_policy == "supplementalPool" else "❌ MISSING (requires OCP 4.19+)")

    # cpu topology (only if in rules)
    if checks.get("cpu"):
        sockets_val = cpu.get("sockets", "not set")
        try:
            sockets_int = int(sockets_val)
            sockets_ok = sockets_int == 1
        except (TypeError, ValueError):
            sockets_ok = False
        row("cpu.sockets", str(sockets_val), "1 (use cores, not sockets)",
            "✅ OK" if sockets_ok else "⚠️ >1 — set sockets: 1 and use cores for vCPU count")

    # evictionStrategy (optional)
    if checks.get("evictionStrategy") == "LiveMigrate":
        row("evictionStrategy", eviction or "not set", "LiveMigrate",
            "✅ OK" if eviction == "LiveMigrate" else "⚠️ NOT SET — VM may be shut down on node drain")

    lines.append("")
    lines.append("─" * 65)
    lines.append("RECOMMENDATION")
    lines.append("─" * 65)
    if findings:
        lines.append(f"  Reference: {CHECKS_FILE.relative_to(CHECKS_FILE.parent.parent)}")
        lines.append("")
        lines.append(f"  {'Setting':<35} {'Issue'}")
        lines.append(f"  {'─'*35} {'─'*40}")
        for sev, section, key, detail in findings:
            prefix = "❌" if sev == "FAIL" else "⚠️"
            lines.append(f"  {prefix} {section+'.'+key:<33} {detail}")
    else:
        lines.append("  Configuration matches recommended template.")

    if findings:
        lines.append("")
        lines.append("─" * 65)
        lines.append("CORRECTED VM YAML")
        lines.append("─" * 65)
        lines.append(_generate_corrected_yaml(vm_path, findings))

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
    out  = LOGS_DIR / f"perfx_linux_{ts}.log"
    out.write_text(report, encoding="utf-8")
    print(f"\nReport saved to: {out}")


if __name__ == "__main__":
    main()
