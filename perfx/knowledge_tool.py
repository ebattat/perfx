from pathlib import Path
import glob as _glob

RULES_DIR      = Path(__file__).parent.parent / "rules"
METHODOLOGY_DIR = Path(__file__).parent.parent / "methodology"


def read_rules(topic: str) -> dict:
    """Read rules and methodology files matching a topic keyword."""
    topic_lower = topic.lower()
    results = []

    for directory, label in [(RULES_DIR, "rules"), (METHODOLOGY_DIR, "methodology")]:
        if not directory.exists():
            continue
        for f in sorted(directory.iterdir()):
            if not f.is_file():
                continue
            if topic_lower in f.name.lower() or topic_lower in f.read_text().lower()[:500]:
                results.append({
                    "file": f.name,
                    "source": label,
                    "content": f.read_text(),
                })

    if not results:
        return {"message": f"No rules or methodology found for topic: {topic!r}"}

    return {
        "topic": topic,
        "files_found": len(results),
        "results": results,
    }


def read_file(path: str, max_lines: int = 200) -> dict:
    """Read any file from the filesystem. Supports glob patterns for multiple files."""
    try:
        paths = sorted(_glob.glob(path)) if "*" in path else [path]
        if not paths:
            return {"error": f"No files found matching: {path}"}

        results = []
        for p in paths:
            try:
                content = Path(p).read_text(errors="replace")
                lines = content.splitlines()
                if len(lines) > max_lines:
                    content = "\n".join(lines[:max_lines]) + f"\n... ({len(lines) - max_lines} more lines)"
                results.append({"path": p, "content": content})
            except Exception as e:
                results.append({"path": p, "error": str(e)})

        if len(results) == 1:
            return results[0]
        return {"files": results}

    except Exception as e:
        return {"error": str(e)}
