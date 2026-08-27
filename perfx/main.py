import sys
import os
import argparse
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
from perfx.logger import setup_logging, get_logger
from perfx.client import Agent

_env_path = Path(__file__).parent.parent / ".env"
load_dotenv(_env_path)

log = get_logger("main")

REPORTS_DIR = Path(os.environ.get("PERFX_LOGS_DIR", Path(__file__).parent.parent / "logs"))


def _save_report(content: str, fmt: str, output_dir: str = None):
    report_dir = Path(output_dir) if output_dir else REPORTS_DIR
    report_dir.mkdir(exist_ok=True)
    ext = "md" if fmt == "markdown" else "log"
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    path = report_dir / f"perfx_report_{timestamp}.{ext}"
    path.write_text(content)
    log.info("Report saved to %s", path)
    print(f"\nReport saved to: {path}")


def _cmd_logs(args):
    from perfx.analyzer import analyze
    from perfx.skills.registry import SkillRegistry

    if getattr(args, "list_skills", False):
        registry = SkillRegistry()
        print("Available skills:")
        for skill in registry.list():
            print(f"  {skill.name:15s} — {skill.description}")
        return

    source = args.logs
    if not source:
        log.error("provide a folder/file path with --logs")
        sys.exit(1)

    skill_names = [s.strip() for s in args.skill.split(",")] if args.skill else None
    fmt = args.output or "summary"

    log.info("Analyzing: %s", source)
    report = analyze(source, skill_names=skill_names)

    if fmt == "markdown":
        content = report.to_markdown()
    elif fmt == "text":
        content = report.to_text()
    else:
        content = report.to_summary()

    print(content)
    _save_report(content, fmt, output_dir=getattr(args, "output_dir", None))


def _cluster_available():
    """Return True if oc is available and logged into a cluster."""
    import subprocess
    try:
        result = subprocess.run(
            ["oc", "whoami"], capture_output=True, text=True, timeout=5
        )
        return result.returncode == 0
    except Exception:
        return False


def _collect_cluster_summary():
    """Collect live cluster data via oc and print a summary using the ocp-data skill parser."""
    import importlib.util
    import subprocess

    def _oc_json(cmd):
        """Run an oc command and return parsed JSON or None."""
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            return __import__("json").loads(result.stdout) if result.returncode == 0 else None
        except Exception:
            return None

    script = Path(__file__).parent.parent / "skills" / "ocp-data" / "collect_ocp_data.py"
    if not script.exists():
        return
    try:
        spec = importlib.util.spec_from_file_location("collect_ocp_data", script)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        version_data = _oc_json(["oc", "version", "-o", "json"]) or {}
        csv_data     = _oc_json(["oc", "get", "csv", "-n", "openshift-cnv", "-o", "json"]) or {}
        nodes_data   = _oc_json(["oc", "get", "nodes", "-o", "json"]) or {}
        vmis_data    = _oc_json(["oc", "get", "vmi", "-A", "-o", "json"])

        ocpv   = mod.parse_ocp_version(version_data)
        cnvv   = mod.parse_cnv_version(csv_data)
        nodes  = mod.parse_nodes(nodes_data)
        counts = mod.parse_vm_counts(vmis_data) if vmis_data is not None else {}

        if not nodes:
            print("⚠️  Could not reach cluster (oc not logged in or unavailable)\n")
            return

        print("─" * 60)
        print("Cluster Summary")
        print("─" * 60)
        print(f"  OCP Version   {ocpv}")
        print(f"  CNV Version   {cnvv}")
        print(f"  Total Nodes   {len(nodes)}")
        print(f"  Total VMs     {sum(counts.values())}")
        print()

        mod.print_table(nodes, counts)
        print()

        # ── analysis ──────────────────────────────────────────────────────────
        print("Cluster Analysis")
        print("─" * 60)
        workers  = [n for n in nodes if n["role"] == "worker"]
        masters  = [n for n in nodes if n["role"] == "control-plane"]

        if workers:
            cpus = [int(n["cpu"]) for n in workers]
            mems = [int(n["memory"].replace("Gi", "")) for n in workers]
            total_vms = sum(counts.values())
            print(f"  Workers:      {len(workers)} nodes | {cpus[0]} CPUs | {mems[0]}Gi memory each")
            print(f"  Masters:      {len(masters)} nodes")
            print(f"  Running VMs:  {total_vms}")

            # check node imbalance
            vm_per_node = {n["name"]: counts.get(n["name"], 0) for n in workers}
            if vm_per_node:
                max_node = max(vm_per_node, key=vm_per_node.get)
                min_node = min(vm_per_node, key=vm_per_node.get)
                if vm_per_node[max_node] > vm_per_node[min_node] + 3:
                    print(f"  ⚠️  VM imbalance: {max_node} has {vm_per_node[max_node]} VMs vs {min_node} has {vm_per_node[min_node]}")

            # check kernel consistency
            kernels = {n["kernel"] for n in nodes}
            if len(kernels) > 1:
                print(f"  ⚠️  Mixed kernel versions: {', '.join(kernels)}")
            else:
                print(f"  ✅  Kernel:      consistent ({next(iter(kernels))})")

            # check OS consistency
            os_versions = {n["os"] for n in nodes}
            if len(os_versions) > 1:
                print(f"  ⚠️  Mixed OS versions across nodes")
            else:
                print(f"  ✅  OS:          consistent")

        print()
        print("Recommendations")
        print("─" * 60)
        recs = []

        # OCP version
        if "ec." in ocpv or "alpha" in ocpv or "beta" in ocpv:
            recs.append(f"⚠️  OCP {ocpv} is a pre-release version — not recommended for production workloads")

        # mixed kernel/OS
        if workers:
            kernels = {n["kernel"] for n in nodes}
            os_versions = {n["os"] for n in nodes}
            if len(kernels) > 1:
                recs.append("⚠️  Mixed kernel versions — update all nodes to the same version before investigating performance issues")
            if len(os_versions) > 1:
                recs.append("⚠️  Mixed OS versions — some nodes may be pending updates; run `oc adm upgrade` to check")

        # VM imbalance
        if workers and total_vms > 0:
            vm_per_node = {n["name"]: counts.get(n["name"], 0) for n in workers}
            max_vms = max(vm_per_node.values())
            min_vms = min(vm_per_node.values())
            if max_vms > min_vms + 3:
                recs.append(f"⚠️  VM imbalance across worker nodes — check scheduler affinity rules")

        # low VM density
        if workers and total_vms == 0:
            recs.append("ℹ️  No VMs running — start a VM to begin performance analysis")

        # memory headroom
        if workers:
            for n in workers:
                alloc_mem = int(n["alloc_mem"].replace("Gi", ""))
                total_mem = int(n["memory"].replace("Gi", ""))
                overhead = total_mem - alloc_mem
                if overhead > 30:
                    recs.append(f"ℹ️  {n['name']}: {overhead}Gi reserved as system overhead — expected for large nodes")
                    break

        if recs:
            for r in recs:
                print(f"  {r}")
        else:
            print("  ✅  Cluster looks healthy — no issues detected")

        print("─" * 60)
        print()

    except Exception as exc:
        log.debug("Cluster summary failed: %s", exc)


def main():
    setup_logging()

    parser = argparse.ArgumentParser(description="PerfX — performance knowledge base agent")
    parser.add_argument("--model", "-m", choices=["gemini", "claude"], default=None)
    parser.add_argument("--logs", metavar="PATH", help="Analyze log files (no agent required)")
    parser.add_argument("--skill", "-s", help="Comma-separated skill names (default: all)")
    parser.add_argument("--output", "-o", choices=["text", "markdown", "summary"], default="summary")
    parser.add_argument("--output-dir", metavar="DIR", help="Directory to save report (default: logs/)")
    args = parser.parse_args()

    if args.model:
        os.environ["PERFBOT_MODEL"] = args.model

    if args.logs:
        _cmd_logs(args)
        return

    model_name = os.environ.get("PERFBOT_MODEL", "claude").lower()
    print(f"PerfX Agent (powered by {model_name.capitalize()}). Type 'exit' or Ctrl-C to quit.")
    from perfx.client import _parse_repos
    repos = [r for r in _parse_repos() if "your-org" not in r]
    if repos:
        print(f"Configured repos: {', '.join(repos)}")
    print()

    REPORTS_DIR.mkdir(exist_ok=True)
    session_ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    session_log = REPORTS_DIR / f"perfx_session_{session_ts}.log"
    session_file = None

    try:
        if _cluster_available():
            answer = input("I noticed a running cluster — analyze it? (y/N): ").strip().lower()
            if answer in ("y", "yes"):
                _collect_cluster_summary()
    except (KeyboardInterrupt, EOFError):
        pass

    agent = Agent()
    while True:
        try:
            user_input = input("You: ").strip()
        except (KeyboardInterrupt, EOFError):
            if session_file:
                session_file.close()
            print("\nBye!")
            sys.exit(0)

        if not user_input:
            continue
        if user_input.lower() in {"exit", "quit"}:
            if session_file:
                session_file.close()
            print("Bye!")
            sys.exit(0)

        try:
            response = agent.chat(user_input)
            print(f"\nAgent: {response}\n")
            # only write log when a skill is invoked (starts with /)
            if user_input.startswith("/"):
                if session_file is None:
                    session_file = open(session_log, "w")
                    session_file.write(f"PerfX Session — {session_ts}\n{'='*60}\n\n")
                    print(f"Session log: {session_log}\n")
                session_file.write(f"You: {user_input}\n\nAgent: {response}\n\n{'─'*60}\n\n")
                session_file.flush()
        except Exception as exc:
            log.exception("Agent error")
            print(f"\n[Error] {exc}\n")


if __name__ == "__main__":
    main()
