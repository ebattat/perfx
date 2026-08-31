#!/usr/bin/env python3
"""
Check Windows VM YAML configuration against rules/windows-vm-checks.yaml.
Usage: python3 check_windows_vm_config.py <customer-vm.yaml>
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


RULES_DIR = Path(__file__).parent.parent.parent / "rules"
LOGS_DIR  = Path(os.environ.get("PERFX_LOGS_DIR", Path(__file__).parent.parent.parent / "logs"))
CHECKS_FILE = RULES_DIR / "windows-vm-checks.yaml"

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


def _detect_os(vm_path):
    """Detect VM OS — returns 'windows', 'linux', or 'unknown'."""
    doc = _load(vm_path)
    domain = (doc.get("spec", {}).get("template", {}).get("spec", {}).get("domain", {}))
    if domain.get("features", {}).get("hyperv"):
        return "windows"
    preference = (doc.get("spec") or {}).get("preference", {}).get("name", "")
    if "windows" in preference.lower():
        return "windows"
    os_label = ((doc.get("spec") or {}).get("template", {})
                .get("metadata", {}).get("annotations", {})
                .get("vm.kubevirt.io/os", ""))
    if os_label and "windows" in os_label.lower():
        return "windows"
    if os_label and os_label not in ("", "__template__"):
        return "linux"
    return "unknown"


def _generate_corrected_yaml(vm_path, findings):
    """Generate corrected VM YAML with fixes applied."""
    import copy
    doc = _load(vm_path)
    domain = _domain(doc)
    changes = []
    checks = _load_checks()

    failed = {(section, key) for sev, section, key, _ in findings if sev == "FAIL"}

    # clock
    if ("clock", "hpet") in failed or ("clock", "hyperv") in failed:
        domain["clock"] = {
            "timer": {
                "hpet": {"present": False},
                "hyperv": {},
                "pit": {"tickPolicy": "delay"},
                "rtc": {"tickPolicy": "catchup"},
            },
            "utc": {},
        }
        changes.append("clock")

    # hyperv
    hyperv_rules = checks.get("features", {}).get("hyperv", {})
    hyperv_missing = [key for sev, section, key, _ in findings if sev == "FAIL" and section == "hyperv"]
    if hyperv_missing:
        features = domain.setdefault("features", {})
        hyperv = features.setdefault("hyperv", {})
        for key in hyperv_missing:
            if key == "spinlocks":
                hyperv[key] = {"spinlocks": hyperv_rules.get("spinlocks", {}).get("spinlocks", 8191)}
            elif key == "synictimer":
                hyperv[key] = {"direct": {}}
            else:
                hyperv[key] = {}
        features.setdefault("acpi", {})
        features.setdefault("apic", {})
        features.setdefault("smm", {})
        changes.append("hyperv enlightenments")

    # ioThreads
    cpu = domain.get("cpu", {})
    vcpus = _to_int(cpu.get("cores", 1), 1) * _to_int(cpu.get("sockets", 1), 1)
    if ("ioThreads", "ioThreadsPolicy") in failed:
        domain["ioThreadsPolicy"] = "supplementalPool"
        domain["ioThreads"] = {"supplementalPoolThreadCount": max(2, vcpus // 4)}
        changes.append("ioThreads")

    # autoattachMemBalloon
    if ("devices", "autoattachMemBalloon") in failed:
        domain.setdefault("devices", {})["autoattachMemBalloon"] = False
        changes.append("autoattachMemBalloon")

    # blockMultiQueue
    if ("devices", "blockMultiQueue") in failed:
        domain.setdefault("devices", {})["blockMultiQueue"] = True
        changes.append("blockMultiQueue")

    # root disk: no automatic cache change — add to rules/windows-vm-checks.yaml if needed

    # clean kubernetes metadata
    meta = doc.get("metadata", {})
    for field in ["managedFields", "resourceVersion", "uid", "creationTimestamp",
                  "generation", "finalizers", "annotations"]:
        meta.pop(field, None)
    doc.pop("status", None)

    raw = yaml.dump(doc, default_flow_style=False, sort_keys=False).rstrip()

    # add inline comments — only for lines that were actually changed
    comments = {}
    if "clock" in changes:
        comments.update({
            "present: false":    "# ADDED: HPET must be disabled",
            "hyperv: {}":        "# ADDED: hypervclock must be present",
            "tickPolicy: delay": "# ADDED: PIT timer policy",
            "tickPolicy: catchup": "# ADDED: RTC timer policy",
            "utc: {}":           "# ADDED: UTC clock",
        })
    if "hyperv enlightenments" in changes:
        comments.update({
            "ipi: {}":           "# ADDED: hyperv enlightenment",
            "synic: {}":         "# ADDED: hyperv enlightenment",
            "synictimer:":       "# ADDED: hyperv enlightenment",
            "direct: {}":        "# ADDED: synictimer direct mode",
            "spinlocks:":        "# ADDED: hyperv enlightenment",
            "spinlocks: 8191":   "# ADDED: must be 8191",
            "reenlightenment: {}": "# ADDED: hyperv enlightenment",
            "reset: {}":         "# ADDED: hyperv enlightenment",
            "relaxed: {}":       "# ADDED: hyperv enlightenment",
            "vpindex: {}":       "# ADDED: hyperv enlightenment",
            "runtime: {}":       "# ADDED: hyperv enlightenment",
            "tlbflush: {}":      "# ADDED: hyperv enlightenment",
            "frequencies: {}":   "# ADDED: hyperv enlightenment",
            "vapic: {}":         "# ADDED: hyperv enlightenment",
        })
    if "ioThreads" in changes:
        comments.update({
            "ioThreadsPolicy: supplementalPool": "# ADDED: offloads IO from vCPU threads",
            "supplementalPoolThreadCount:": f"# ADDED: {max(2, vcpus // 4)} threads for {vcpus} vCPUs (min 2, scale up for fast storage)",
        })
    if "autoattachMemBalloon" in changes:
        comments["autoattachMemBalloon: false"] = "# ADDED: must be false for MSSQL"
    if "blockMultiQueue" in changes:
        comments["blockMultiQueue: true"] = "# ADDED: enables multi-queue for block devices"

    annotated = []
    for line in raw.splitlines():
        stripped = line.strip()
        comment = next((v for k, v in comments.items()
                        if stripped == k
                        or stripped.startswith(k + " ")
                        or stripped.startswith(k + ":")
                        or stripped == k + ":"
                        or (": " in k and stripped == k)), None)
        if comment and not line.strip().startswith("#"):
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

    devices    = domain.get("devices") or {}
    features   = domain.get("features") or {}
    hyperv_cfg = features.get("hyperv") or {}
    clock      = domain.get("clock") or {}
    timer      = clock.get("timer") or {}
    firmware   = domain.get("firmware") or {}
    bootloader = firmware.get("bootloader") or {}
    cpu        = domain.get("cpu") or {}
    io_policy  = domain.get("ioThreadsPolicy")
    io_count   = (domain.get("ioThreads") or {}).get("supplementalPoolThreadCount")

    def _fail(section, key, detail):
        findings.append(("FAIL", section, key, detail))

    def _warn(section, key, detail):
        findings.append(("WARN", section, key, detail))

    def _ok(section, key):
        passes.append((section, key))

    # ── devices checks from rules ─────────────────────────────────────────────
    dev_rules = checks.get("devices", {})

    # autoattachMemBalloon
    balloon = devices.get("autoattachMemBalloon")
    exp = dev_rules.get("autoattachMemBalloon")
    if exp is not None:
        if balloon != exp:
            _fail("devices", "autoattachMemBalloon", f"={balloon!r} (want {exp!r} — must be disabled for MSSQL)")
        else:
            _ok("devices", "autoattachMemBalloon")

    # blockMultiQueue
    bmq = devices.get("blockMultiQueue")
    exp = dev_rules.get("blockMultiQueue")
    if exp is not None:
        if bmq != exp:
            _fail("devices", "blockMultiQueue", f"={bmq!r} (want {exp!r})")
        else:
            _ok("devices", "blockMultiQueue")

    # tpm
    tpm = devices.get("tpm")
    if dev_rules.get("tpm") == "required":
        if tpm is None:
            _fail("devices", "tpm", "tpm section missing")
        else:
            _ok("devices", "tpm")

    # networkInterfaceMultiqueue
    net_mq = devices.get("networkInterfaceMultiqueue")
    exp = dev_rules.get("networkInterfaceMultiqueue")
    if exp is not None:
        if net_mq != exp:
            _fail("devices", "networkInterfaceMultiqueue", f"={net_mq!r} (want {exp!r})")
        else:
            _ok("devices", "networkInterfaceMultiqueue")

    # NIC model
    interfaces = devices.get("interfaces") or []
    nic_models = {iface.get("model", "virtio") for iface in interfaces}
    bad_nics = nic_models & {"e1000", "e1000e", "rtl8139"}
    if bad_nics:
        _fail("devices", "NIC model", f"non-virtio NIC ({', '.join(sorted(bad_nics))}) — switch to model: virtio")
    else:
        _ok("devices", "NIC model")

    # disk bus
    disks = devices.get("disks") or []
    bus_vals = list({(d.get("disk") or {}).get("bus", "?") for d in disks})
    ok_bus = all(b in ("virtio", "scsi") for b in bus_vals)
    if not ok_bus:
        _warn("devices", "disk bus", f"non-virtio/scsi bus detected: {', '.join(bus_vals)}")
    else:
        _ok("devices", "disk bus")

    # ── clock checks ─────────────────────────────────────────────────────────
    clock_rules = checks.get("clock", {}).get("timer", {})
    has_hpet = "hpet" in timer
    has_hyperv_t = "hyperv" in timer
    has_pit = "pit" in timer
    has_rtc = "rtc" in timer

    if not (has_hpet and has_hyperv_t and has_pit and has_rtc):
        _fail("clock", "hpet", "timer 'hpet' not present") if not has_hpet else None
        _fail("clock", "hyperv", "timer 'hyperv' not present") if not has_hyperv_t else None
        _fail("clock", "pit", "timer 'pit' not present") if not has_pit else None
        _fail("clock", "rtc", "timer 'rtc' not present") if not has_rtc else None
    else:
        # check specific values
        hpet_present = (timer.get("hpet") or {}).get("present")
        if hpet_present is not False:
            _fail("clock", "hpet", f"hpet.present={hpet_present!r} (want false)")
        else:
            _ok("clock", "hpet")
        pit_policy = (timer.get("pit") or {}).get("tickPolicy")
        if pit_policy != "delay":
            _fail("clock", "pit", f"pit.tickPolicy={pit_policy!r} (want 'delay')")
        else:
            _ok("clock", "pit")
        rtc_policy = (timer.get("rtc") or {}).get("tickPolicy")
        if rtc_policy != "catchup":
            _fail("clock", "rtc", f"rtc.tickPolicy={rtc_policy!r} (want 'catchup')")
        else:
            _ok("clock", "rtc")
        _ok("clock", "hyperv")

    # ── firmware ─────────────────────────────────────────────────────────────
    efi  = "efi" in bootloader
    bios = "bios" in bootloader
    if not efi:
        if bios:
            _warn("firmware", "bootloader", "using legacy BIOS (want EFI)")
        else:
            _warn("firmware", "bootloader", "unknown firmware type (want EFI)")
    else:
        _ok("firmware", "bootloader")

    # ── machine type ─────────────────────────────────────────────────────────
    mtype = (domain.get("machine") or {}).get("type", "")
    _min_mtype = "pc-q35-rhel9.8.0"
    mtype_ok = bool(mtype) and mtype >= _min_mtype
    if not mtype_ok:
        _warn("machine", "type", f"={mtype!r} — too old for OCP 4.22 coalescing (need {_min_mtype}+)")
    else:
        _ok("machine", "type")

    # ── ioThreads ────────────────────────────────────────────────────────────
    if io_policy != "supplementalPool":
        _fail("ioThreads", "ioThreadsPolicy", f"={io_policy!r} (want 'supplementalPool')")
    else:
        _ok("ioThreads", "ioThreadsPolicy")

    vcpus = _to_int(cpu.get("cores", 1), 1) * _to_int(cpu.get("sockets", 1), 1)
    rec_threads = max(2, min(vcpus // 4, 16)) if vcpus > 1 else 2
    if not io_count:
        _fail("ioThreads", "supplementalPoolThreadCount", f"not set (want ≥{rec_threads} based on {vcpus} vCPUs)")
    else:
        _ok("ioThreads", "supplementalPoolThreadCount")

    # ── cpu topology ─────────────────────────────────────────────────────────
    cpu_rules = checks.get("cpu", {})
    if cpu_rules:
        sockets = cpu.get("sockets", 1)
        threads = cpu.get("threads", 1)
        try:
            sockets = int(sockets)
            threads = int(threads)
        except (TypeError, ValueError):
            sockets = threads = 1
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

    # ── hyperv enlightenments ─────────────────────────────────────────────────
    hyperv_rules = checks.get("features", {}).get("hyperv", {})
    required_hv = [k for k, v in hyperv_rules.items() if v == "required" or isinstance(v, dict)]
    for key in required_hv:
        if key not in hyperv_cfg:
            _fail("hyperv", key, f"missing from features.hyperv")
        elif key == "spinlocks":
            val = (hyperv_cfg[key] or {}).get("spinlocks") if isinstance(hyperv_cfg[key], dict) else None
            expected_val = hyperv_rules.get("spinlocks", {}).get("spinlocks", 8191)
            if val != expected_val:
                _fail("hyperv", key, f"spinlocks={val} (want {expected_val})")
            else:
                _ok("hyperv", key)
        elif key == "synictimer":
            direct = isinstance(hyperv_cfg.get(key), dict) and "direct" in hyperv_cfg[key]
            if not direct:
                _fail("hyperv", key, "missing 'direct: {}' inside synictimer")
            else:
                _ok("hyperv", key)
        else:
            _ok("hyperv", key)

    # ── output ────────────────────────────────────────────────────────────────
    lines = []
    lines.append("=" * 65)
    lines.append("WINDOWS VM CONFIGURATION AUDIT")
    lines.append("=" * 65)
    lines.append(f"\nVM        : {vm_name}")
    lines.append(f"File      : {vm_path}")
    lines.append(f"Reference : {CHECKS_FILE}")
    fails = sum(1 for s, *_ in findings if s == "FAIL")
    warns = sum(1 for s, *_ in findings if s == "WARN")
    severity = "CRITICAL" if fails > 0 else ("WARNING" if warns > 0 else "OK")
    lines.append(f"\nResult    : {fails} critical issue(s), {warns} warning(s), {len(passes)} check(s) passed")
    lines.append(f"Severity  : {severity}\n")

    lines.append(f"  {'Setting':<28} {'Customer VM':<45} {'Recommended':<50} Status")
    lines.append(f"  {'─'*28} {'─'*45} {'─'*50} {'─'*40}")

    table_rows = []
    extra_lines = {}  # setting → extra continuation lines

    def row(setting, customer, recommended, status, extra=None):
        table_rows.append((setting, customer, recommended, status))
        if extra:
            extra_lines[setting] = extra

    # clock row
    clock_str = "hpet+hyperv+pit+rtc" if (has_hpet and has_hyperv_t and has_pit and has_rtc) else clock.get("timezone", "UTC")
    clock_ok = not any(s == "FAIL" and sec == "clock" for s, sec, *_ in findings)
    row("clock", clock_str, "hpet:false + hyperv + pit + rtc",
        "✅ OK" if clock_ok else "❌ MISSING — no timer config")

    # hyperv enlightenments row
    present_hv = [k for k in required_hv if k in hyperv_cfg]
    missing_hv = [k for k in required_hv if k not in hyperv_cfg]
    all_hv_str = f"all {len(required_hv)} enlightenments"
    if not missing_hv:
        row("hyperv enlightenments", f"all {len(required_hv)} present", all_hv_str, "✅ OK")
    elif not present_hv:
        keys_str = ", ".join(required_hv[:4])
        row("hyperv enlightenments", "None", all_hv_str, "❌ MISSING — no hyperv features at all",
            extra=f"  {'':28} {'':45} {keys_str},")
    else:
        row("hyperv enlightenments", f"{len(present_hv)}/{len(required_hv)} present",
            all_hv_str, f"❌ PARTIAL — missing: {', '.join(missing_hv[:3])}...")

    # ioThreads rows
    rec_io_str = f"≥{rec_threads} (based on {vcpus} vCPUs)"
    row("ioThreads", str(io_count) if io_count else "None", rec_io_str,
        "✅ OK" if io_count else "❌ MISSING (requires OCP 4.19+)")
    row("ioThreadsPolicy", str(io_policy) if io_policy else "None", "supplementalPool",
        "✅ OK" if io_policy == "supplementalPool" else "❌ MISSING (requires OCP 4.19+)")

    # autoattachMemBalloon
    balloon_str = str(balloon).lower() if balloon is not None else "Not set (defaults to true)"
    row("autoattachMemBalloon", balloon_str, "false",
        "✅ OK" if balloon is False else "❌ MISSING")

    # blockMultiQueue
    row("blockMultiQueue", str(bmq).lower() if bmq is not None else "not set", "true",
        "✅ OK" if bmq is True else "❌ MISSING")

    # tpm
    row("tpm", "present" if tpm is not None else "missing", "required",
        "✅ OK" if tpm is not None else "❌ MISSING")

    # disk bus
    bus_str = ", ".join(bus_vals) if bus_vals else "not set"
    row("disk bus", bus_str, "virtio (or scsi for OCP 4.22)",
        "✅ OK" if ok_bus else "⚠️ CHECK")

    # machine type
    row("machine type", mtype or "not set", f"{_min_mtype}+",
        "✅ OK" if mtype_ok else "⚠️ OLD — too old for OCP 4.22 coalescing")

    # firmware
    fw_str = "efi" if efi else ("bios: {}" if bios else "not set")
    row("firmware", fw_str, "efi: {secureBoot: false}",
        "✅ OK" if efi else "⚠️ Using legacy BIOS, not EFI")

    # networkInterfaceMultiqueue
    row("networkInterfaceMultiqueue", str(net_mq).lower() if net_mq is not None else "not set", "true",
        "✅ OK" if net_mq is True else "⚠️ NOT SET")

    # NIC model
    nic_str = ", ".join(sorted(nic_models)) if nic_models else "virtio (default)"
    row("NIC model", nic_str, "virtio",
        "❌ WRONG MODEL" if bad_nics else "✅ OK")

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

    # sort: ❌ first, ⚠️ second, ✅ last
    def _sort_key(r):
        s = r[3]
        if s.startswith("❌"): return 0
        if s.startswith("⚠️"): return 1
        return 2
    for setting, customer, recommended, status in sorted(table_rows, key=_sort_key):
        lines.append(f"  {setting:<28} {customer:<45} {recommended:<50} {status}")
        if setting in extra_lines:
            lines.append(extra_lines[setting])

    lines.append("")
    lines.append("─" * 65)
    lines.append("RECOMMENDATION")
    lines.append("─" * 65)
    if findings:
        lines.append(f"  Reference: {CHECKS_FILE.relative_to(CHECKS_FILE.parent.parent)}")
        lines.append("")
        lines.append("  FINDINGS:")
        lines.append(f"  {'Setting':<35} {'Issue'}")
        lines.append(f"  {'─'*35} {'─'*40}")
        for sev, section, key, detail in findings:
            prefix = "❌" if sev == "FAIL" else "⚠️"
            lines.append(f"  {prefix} {section+'.'+key:<33} {detail}")
    else:
        lines.append("  Configuration matches recommended template.")

    lines.append("")
    lines.append("─" * 65)
    lines.append("GUEST-SIDE STEPS (always required for Windows VMs)")
    lines.append("─" * 65)
    lines.append("  1. Remove platform clock override (run inside guest, then reboot):")
    lines.append("       bcdedit /deletevalue useplatformclock")
    lines.append("  2. Verify VBS is disabled (run inside Windows guest, then reboot):")
    lines.append("       msinfo32 → Virtualization-based security: Not enabled")
    lines.append("     To disable: Windows Security → Device Security → Core isolation")
    lines.append("                 → Memory integrity → Off  (then reboot)")
    lines.append("  3. Apply C1 tuned profile on worker nodes (pins CPUs to C1 for low latency):")
    lines.append("       oc apply -f skills/ocp-analysis/tuned-c1.yaml")
    lines.append("     Verify: oc get profile.tuned.openshift.io -n openshift-cluster-node-tuning-operator")

    if any(s == "FAIL" for s, *_ in findings):
        lines.append("")
        lines.append("─" * 65)
        lines.append("CORRECTED VM YAML")
        lines.append("─" * 65)
        corrected = _generate_corrected_yaml(vm_path, findings)
        lines.append(corrected)

    total_checks = len(findings) + len(passes)
    lines.append("")
    lines.append("─" * 65)
    lines.append("SUMMARY")
    lines.append("─" * 65)
    lines.append(f"  {len(passes)}/{total_checks} checks passed — {fails} critical, {warns} warning(s)")

    return "\n".join(lines)


def _list_vms():
    """List all running VMs across all namespaces via oc CLI."""
    import subprocess
    try:
        result = subprocess.run(
            ["oc", "get", "vm", "--all-namespaces", "-o", "wide"],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            print(f"ERROR: {result.stderr.strip()}", file=sys.stderr)
            sys.exit(1)
        print(result.stdout)
    except FileNotFoundError:
        print("ERROR: 'oc' not found — is OpenShift CLI installed?", file=sys.stderr)
        sys.exit(1)


def _fetch_vm_yaml(name, namespace):
    """Fetch VM YAML from cluster via oc CLI and return a temp file path."""
    import subprocess
    import tempfile
    try:
        result = subprocess.run(
            ["oc", "get", "vm", name, "-n", namespace, "-o", "yaml"],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            print(f"ERROR: {result.stderr.strip()}", file=sys.stderr)
            sys.exit(1)
        tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False)
        tmp.write(result.stdout)
        tmp.close()
        return tmp.name
    except FileNotFoundError:
        print("ERROR: 'oc' not found — is OpenShift CLI installed?", file=sys.stderr)
        sys.exit(1)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Check Windows VM YAML against best practices")
    parser.add_argument("vm_yaml", help="Path to VM YAML file")
    parser.add_argument("--os", choices=["windows", "linux"], help="Override OS detection")
    args = parser.parse_args()

    vm_path = args.vm_yaml

    detected_os = args.os or _detect_os(vm_path)
    if detected_os == "linux":
        print("ERROR: VM detected as Linux — use check_linux_vm_config.py for Linux VMs.",
              file=sys.stderr)
        sys.exit(1)
    if detected_os == "unknown":
        print("Note: OS not detected from YAML — running Windows check (use --os to override).")

    report = check(vm_path)
    print(report)

    LOGS_DIR.mkdir(exist_ok=True)
    ts  = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    out = LOGS_DIR / f"perfx_{ts}.log"
    out.write_text(report)
    print(f"\nReport saved to: {out}")


if __name__ == "__main__":
    main()
