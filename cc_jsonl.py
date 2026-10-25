"""Shared transcript reader for burn-ledger and error-tail (keep the two copies byte-identical).

Reads Claude Code session files (*.jsonl). Real layout: <projects>/<project folder>/<session id>.jsonl, so one
project folder holds many sessions. Stdlib only. Reads and yields records; never prints content.
"""
import json
from datetime import datetime, timezone
from pathlib import Path


def parse_ts(text):
    """One reading of time for every tool: an aware UTC datetime, or None. A time without a zone is UTC
    (Claude Code writes ...Z; the tools used to read the rest three different ways)."""
    if not text:
        return None
    try:
        dt = datetime.fromisoformat(str(text).strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return (dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt).astimezone(timezone.utc)


def iter_records(root):
    """Yield (session, project, record) for every record under root.

    session: the record's own sessionId; if the record has none, the file name without .jsonl;
             a sub-agent file (folder named subagents/) with no sessionId counts to its parent session folder.
    project: the first folder under root; '' for files that sit directly in root.
    """
    root = Path(root)
    if not root.is_dir():                       # a wrong --dir must not read as "no sessions"
        raise FileNotFoundError(f"not found: {root}")
    for path in sorted(root.rglob("*.jsonl")):
        parts = path.relative_to(root).parts
        project = parts[0] if len(parts) > 1 else ""
        fallback = path.stem
        if "subagents" in parts and parts.index("subagents") >= 1:
            fallback = parts[parts.index("subagents") - 1]
        for rec in read_records(path):
            yield str(rec.get("sessionId") or fallback), project, rec


def usage_key(rec):
    """Streamed copies of one assistant message share message.id (+ requestId when it is written); None without an id.
    A record with an id but no requestId is still one message: four such copies counted four times before."""
    msg = rec.get("message") or {}
    return (msg["id"], rec.get("requestId") or "") if msg.get("id") else None


def _output(rec):
    return int(((rec.get("message") or {}).get("usage") or {}).get("output_tokens") or 0)


def unique_usage(records):
    """(session, project, rec) with usage, one per streamed message: the copy with the most output_tokens
    (all copies were equal on Claude Code 2.1.300-2.1.310; a growing count would be read right too).
    Returns (rows, duplicates_dropped)."""
    best, rows, dropped = {}, [], 0
    for session, project, rec in records:
        if not isinstance((rec.get("message") or {}).get("usage"), dict):
            continue
        key = usage_key(rec)
        if key is None:
            rows.append((session, project, rec))
        elif key in best:
            dropped += 1
            if _output(rec) > _output(best[key][2]):
                best[key] = (session, project, rec)
        else:
            best[key] = (session, project, rec)
    return rows + list(best.values()), dropped


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
