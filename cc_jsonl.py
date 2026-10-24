"""Shared transcript reader for burn-ledger and error-tail (keep the two copies byte-identical).

Reads Claude Code session files (*.jsonl). Real layout: <projects>/<project folder>/<session id>.jsonl, so one
project folder holds many sessions. Stdlib only. Reads and yields records; never prints content.
"""
import json
from pathlib import Path


def iter_records(root):
    """Yield (session, project, record) for every record under root.

    session: the record's own sessionId; if the record has none, the file name without .jsonl;
             a sub-agent file (folder named subagents/) with no sessionId counts to its parent session folder.
    project: the first folder under root; '' for files that sit directly in root.
    """
    root = Path(root)
    for path in sorted(root.rglob("*.jsonl")):
        parts = path.relative_to(root).parts
        project = parts[0] if len(parts) > 1 else ""
        fallback = path.stem
        if "subagents" in parts and parts.index("subagents") >= 1:
            fallback = parts[parts.index("subagents") - 1]
        for rec in read_records(path):
            yield str(rec.get("sessionId") or fallback), project, rec


def read_records(path):
    """Yield dict records from one jsonl file. Lines that are not JSON objects are skipped."""
    with open(path, encoding="utf-8", errors="replace") as fh:
        for raw in fh:
            raw = raw.strip()
            if not raw:
                continue
            try:
                rec = json.loads(raw)
            except ValueError:
                continue
            if isinstance(rec, dict):
                yield rec
