#!/usr/bin/env python3
"""
Compare a customer Windows VM YAML against the recommended template.
Usage: python3 check_vm_config.py <customer-vm.yaml>
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


RULES_DIR = Path(__file__).parent.parent.parent / "rules"
LOGS_DIR  = Path(__file__).parent.parent.parent / "logs"

REQUIRED_HYPERV = [
    "ipi", "synic", "synictimer", "spinlocks", "reenlightenment",
    "reset", "relaxed", "vpindex", "runtime", "tlbflush", "frequencies", "vapic",
]

REQUIRED_TIMERS = {
    "hpet":       ("present", False),
    "hyperv":     None,
    "pit":        ("tickPolicy", "delay"),
    "rtc":        ("tickPolicy", "catchup"),
}


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


def check(vm_path):
    doc    = _load(vm_path)
    domain = _domain(doc)
    vm_name = doc.get("metadata", {}).get("name", Path(vm_path).stem)

    findings = []
    passes   = []

    # ── hyperv enlightenments ─────────────────────────────────
    hyperv = (domain.get("features", {}) or {}).get("hyperv") or {}
    for key in REQUIRED_HYPERV:
        if key not in hyperv:
            findings.append(("FAIL", "hyperv", key, f"missing from features.hyperv"))
        elif key == "spinlocks":
            val = (hyperv[key] or {}).get("spinlocks") if isinstance(hyperv[key], dict) else None
            if val != 8191:
                findings.append(("FAIL", "hyperv", key, f"spinlocks={val} (want 8191)"))
            else:
                passes.append(("hyperv", key))
        elif key == "synictimer":
            direct = isinstance(hyperv.get(key), dict) and "direct" in hyperv[key]
            if not direct:
                findings.append(("FAIL", "hyperv", key, "missing 'direct: {}' inside synictimer"))
            else:
                passes.append(("hyperv", key))
        else:
            passes.append(("hyperv", key))

    # ── clock timers ─────────────────────────────────────────
    clock = domain.get("clock", {}) or {}
    timer = clock.get("timer", {}) or {}
    for tname, check_val in REQUIRED_TIMERS.items():
        if tname not in timer:
            findings.append(("FAIL", "clock", tname, f"timer '{tname}' not present"))
        elif check_val is None:
            passes.append(("clock", tname))
        else:
            attr, want = check_val
            got = (timer[tname] or {}).get(attr) if isinstance(timer[tname], dict) else None
            if got != want:
                findings.append(("FAIL", "clock", tname, f"{attr}={got!r} (want {want!r})"))
            else:
                passes.append(("clock", tname))

    # ── ioThreads ─────────────────────────────────────────────
    io_policy = domain.get("ioThreadsPolicy")
    io_threads = (domain.get("ioThreads") or {}).get("supplementalPoolThreadCount")
    if io_policy != "supplementalPool":
        findings.append(("FAIL", "ioThreads", "ioThreadsPolicy",
                          f"={io_policy!r} (want 'supplementalPool')"))
    else:
        passes.append(("ioThreads", "ioThreadsPolicy"))
    if io_threads != 8:
        findings.append(("FAIL", "ioThreads", "supplementalPoolThreadCount",
                          f"={io_threads} (want 8)"))
    else:
        passes.append(("ioThreads", "supplementalPoolThreadCount"))

    # ── autoattachMemBalloon ──────────────────────────────────
    balloon = (domain.get("devices") or {}).get("autoattachMemBalloon")
    if balloon is not False:
        findings.append(("FAIL", "devices", "autoattachMemBalloon",
                          f"={balloon!r} (want false — must be disabled for MSSQL)"))
    else:
        passes.append(("devices", "autoattachMemBalloon"))

    # ── machine type ──────────────────────────────────────────
    mtype = (domain.get("machine") or {}).get("type", "")
    if mtype and mtype < "pc-q35-rhel9.8.0":
        findings.append(("WARN", "machine", "type",
                          f"={mtype!r} — older than pc-q35-rhel9.8.0 (OCP 4.22 coalescing requires 9.8.0+)"))
    else:
        passes.append(("machine", "type"))

    # ── disk bus ──────────────────────────────────────────────
    disks = (domain.get("devices") or {}).get("disks", []) or []
    for disk in disks:
        bus = (disk.get("disk") or {}).get("bus", "")
        if bus not in ("virtio", "scsi"):
            findings.append(("WARN", "disk", disk.get("name", "?"),
                              f"bus={bus!r} (virtio or scsi recommended)"))

    # ── output ────────────────────────────────────────────────
    lines = []
    lines.append("=" * 65)
    lines.append("WINDOWS VM CONFIGURATION AUDIT")
    lines.append("=" * 65)
    lines.append(f"\nVM        : {vm_name}")
    lines.append(f"File      : {vm_path}")
    lines.append(f"Reference : {RULES_DIR}/windows-vm-template.yaml")
    lines.append(f"\nResult    : {len(findings)} issue(s), {len(passes)} check(s) passed\n")

    lines.append(f"  {'Setting':<28} {'Customer VM':<45} {'Recommended':<50} Status")
    lines.append(f"  {'─'*28} {'─'*45} {'─'*50} {'─'*40}")

    def row(setting, customer, recommended, status, impact=""):
        lines.append(f"  {setting:<28} {customer:<45} {recommended:<50} {status}")

    # build a lookup for quick access
    domain    = _domain(doc)
    devices   = domain.get("devices") or {}
    hyperv    = (domain.get("features") or {}).get("hyperv") or {}
    clock     = domain.get("clock") or {}
    timer     = clock.get("timer") or {}
    machine   = (domain.get("machine") or {}).get("type", "not set")
    firmware  = domain.get("firmware") or {}
    bootloader= (firmware.get("bootloader") or {})
    memory    = (domain.get("memory") or {}).get("guest", "not set")
    cpu       = domain.get("cpu") or {}
    io_policy = domain.get("ioThreadsPolicy")
    io_count  = (domain.get("ioThreads") or {}).get("supplementalPoolThreadCount")
    balloon   = devices.get("autoattachMemBalloon")
    net_mq    = devices.get("networkInterfaceMultiqueue")
    disks     = devices.get("disks") or []
    bus_vals  = list({(d.get("disk") or {}).get("bus", "?") for d in disks})
    efi       = "efi" in bootloader
    bios      = "bios" in bootloader

    # clock
    has_hpet         = "hpet" in timer
    has_hyperv_timer  = "hyperv" in timer
    has_pit           = "pit" in timer
    has_rtc           = "rtc" in timer
    if has_hpet and has_hyperv_timer and has_pit and has_rtc:
        row("clock", "hpet+hyperv+pit+rtc", "hpet:false + hyperv + pit + rtc", "✅ OK")
    else:
        cval = clock.get("timezone", "timezone only") if not has_hpet else "partial config"
        row("clock", f"{cval}", "hpet:false + hyperv + pit + rtc",
            "❌ MISSING — no timer config")

    # hyperv enlightenments
    present    = [k for k in REQUIRED_HYPERV if k in hyperv]
    missing_hv = [k for k in REQUIRED_HYPERV if k not in hyperv]
    all_hv_short = "all 12 enlightenments (see rules/windows-vm-template.yaml)"
    if not missing_hv:
        row("hyperv enlightenments", f"all {len(REQUIRED_HYPERV)} present", all_hv_short, "✅ OK")
    elif not present:
        row("hyperv enlightenments", "None", all_hv_short, "❌ MISSING — no hyperv features at all")
        lines.append(f"  {'':28} {'':45} ipi, synic, synictimer, spinlocks:8191,")
        lines.append(f"  {'':28} {'':45} reenlightenment, reset, relaxed, vpindex,")
        lines.append(f"  {'':28} {'':45} runtime, tlbflush, frequencies, vapic")
    else:
        missing_str = ", ".join(missing_hv)
        row("hyperv enlightenments", f"{len(present)}/{len(REQUIRED_HYPERV)} present",
            all_hv_short, f"❌ PARTIAL — missing: {missing_str[:30]}...")

    if "spinlocks" in hyperv:
        val = (hyperv["spinlocks"] or {}).get("spinlocks") if isinstance(hyperv["spinlocks"], dict) else None
        if val != 8191:
            row("  spinlocks", str(val), "8191", "❌ WRONG VALUE",
                "Guest spin-loops instead of yielding → wasted CPU under lock contention")

    # ioThreads — recommend based on vCPU count
    vcpus = (cpu.get("cores", 1) or 1) * (cpu.get("sockets", 1) or 1)
    rec_threads = max(4, min(vcpus // 4, 16))
    rec_io_str = f"≥{rec_threads} (based on {vcpus} vCPUs)"
    if not io_count:
        io_status = "❌ MISSING (requires OCP 4.19+)"
        io_impact = "IO on vCPU threads → competes with guest → higher IO latency"
    elif io_count < rec_threads:
        io_status = f"⚠️ LOW — {io_count} set, ≥{rec_threads} recommended"
        io_impact = f"Consider increasing for {vcpus} vCPUs — start at 4, scale up for fast storage"
    else:
        io_status = "✅ OK"
        io_impact = ""
    row("ioThreads", str(io_count) if io_count else "None", rec_io_str, io_status, io_impact)
    row("ioThreadsPolicy", str(io_policy) if io_policy else "None",
        "supplementalPool",
        "✅ OK" if io_policy == "supplementalPool" else "❌ MISSING (requires OCP 4.19+)",
        "" if io_policy == "supplementalPool" else "IO not offloaded → vCPU contention under MSSQL load")

    # autoattachMemBalloon
    balloon_str = str(balloon).lower() if balloon is not None else "Not set (defaults to true)"
    row("autoattachMemBalloon", balloon_str, "false",
        "✅ OK" if balloon is False else "❌ MISSING",
        "" if balloon is False else "Balloon active → MSSQL buffer pool can be shrunk by hypervisor")

    # disk bus
    bus_str = ", ".join(bus_vals) if bus_vals else "not set"
    ok_bus  = all(b in ("virtio", "scsi") for b in bus_vals)
    row("disk bus", bus_str, "virtio (or scsi for OCP 4.22)",
        "✅ OK" if ok_bus else "⚠️ CHECK")

    # machine type
    row("machine type", machine, "pc-q35-rhel9.8.0+",
        "✅ OK" if machine >= "pc-q35-rhel9.8.0" else "⚠️ OLD — too old for OCP 4.22 coalescing")

    # firmware
    efi  = "efi"  in bootloader
    bios = "bios" in bootloader
    if efi:
        row("firmware", "efi", "efi: {secureBoot: false}", "✅ OK")
    elif bios:
        row("firmware", "bios: {}", "efi: {secureBoot: false}",
            "⚠️ Using legacy BIOS, not EFI",
            "Some UEFI features unavailable, TPM limited")
    else:
        row("firmware", "not set", "efi: {secureBoot: false}", "⚠️ UNKNOWN")

    # networkInterfaceMultiqueue
    row("networkInterfaceMultiqueue",
        str(net_mq).lower() if net_mq is not None else "not set",
        "true",
        "✅ OK" if net_mq is True else "⚠️ NOT SET",
        "" if net_mq is True else "Single queue NIC → bottleneck at high connection counts")

    # NIC model
    BAD_NIC_MODELS = {"e1000", "e1000e", "rtl8139"}
    interfaces = devices.get("interfaces") or []
    nic_models = {iface.get("model", "virtio") for iface in interfaces}
    bad_nics = nic_models & BAD_NIC_MODELS
    if bad_nics:
        row("NIC model", ", ".join(sorted(bad_nics)), "virtio",
            "❌ WRONG MODEL",
            f"Non-virtio NIC ({', '.join(sorted(bad_nics))}) causes significant network performance degradation. "
            "Switch to model: virtio")
    else:
        row("NIC model", ", ".join(sorted(nic_models)) if nic_models else "virtio (default)", "virtio", "✅ OK")

    # cpu
    cores   = cpu.get("cores", "?")
    sockets = cpu.get("sockets", "?")
    threads = cpu.get("threads", "?")
    row("cpu", f"{cores} cores, {sockets} socket", "1 socket, 1 thread", "✅ OK")

    # memory
    row("memory", str(memory), "—", "✅ Set" if memory != "not set" else "⚠️ NOT SET")

    lines.append("")
    lines.append("─" * 65)
    lines.append("RECOMMENDATION")
    lines.append("─" * 65)
    if any(s == "FAIL" for s, *_ in findings):
        lines.append("  Apply the recommended Windows VM configuration:")
        lines.append("  https://github.com/redhat-performance/benchmark-runner/blob/main/")
        lines.append("  benchmark_runner/common/template_operations/templates/windows/")
        lines.append("  internal_data/windows_vm_template.yaml")
        lines.append("")
        lines.append("  Key fixes for this VM:")
        for sev, section, key, detail in findings:
            if sev == "FAIL":
                lines.append(f"    • {section}.{key}: {detail}")
    else:
        lines.append("  Configuration matches recommended template.")

    return "\n".join(lines)


def main():
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <vm.yaml>")
        sys.exit(1)

    vm_path = sys.argv[1]
    report  = check(vm_path)
    print(report)

    # save to logs/
    LOGS_DIR.mkdir(exist_ok=True)
    ts   = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    name = Path(vm_path).stem
    out  = LOGS_DIR / f"vm_config_audit_{name}_{ts}.log"
    out.write_text(report)
    print(f"\nReport saved to: {out}")


if __name__ == "__main__":
    main()
