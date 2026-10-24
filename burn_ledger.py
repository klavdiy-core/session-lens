"""burn-ledger: two numbers that `ccusage` does not give.

1. cache_read_share per session: how much of the context a session re-reads from cache (0.00 .. 1.00).
2. concurrency after a limit reset: how many sessions had at least one record in the first N minutes after --since.

Reads Claude Code transcripts (--dir, default ~/.claude/projects). Dedupes streamed copies of one assistant message
by (message.id, requestId). Counts sub-agent (sidechain) files. Prints numbers only, never prompt or output content,
and never a share of any allowance.
"""
import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path

from cc_jsonl import iter_records

DEFAULT_DIR = Path.home() / ".claude" / "projects"
FIELDS = ("input", "output", "cache_create", "cache_read")


def _parse_ts(text):
    try:
        return datetime.fromisoformat(str(text).replace("Z", "+00:00"))
    except ValueError:
        return None


def summarize(root, since=None, window_min=30):
    since_dt = _parse_ts(since) if since else None
    end_dt = since_dt + timedelta(minutes=window_min) if since_dt else None
    seen, dropped, active = set(), 0, set()
    sessions = {}
    for session, project, rec in iter_records(root):
        msg = rec.get("message") or {}
        ts = _parse_ts(rec.get("timestamp"))
        if since_dt and ts and since_dt <= ts < end_dt:
            active.add(session)
        usage = msg.get("usage")
        if not isinstance(usage, dict):
            continue
        key = (msg.get("id"), rec.get("requestId"))
        if key[0] and key[1]:
            if key in seen:
                dropped += 1
                continue
            seen.add(key)
        row = sessions.setdefault(session, dict.fromkeys(FIELDS, 0))
        row.setdefault("project", project)
        row["input"] += int(usage.get("input_tokens") or 0)
        row["output"] += int(usage.get("output_tokens") or 0)
        row["cache_create"] += int(usage.get("cache_creation_input_tokens") or 0)
        row["cache_read"] += int(usage.get("cache_read_input_tokens") or 0)
    for row in sessions.values():
        total = sum(row[f] for f in FIELDS)
        row["cache_read_share"] = round(row["cache_read"] / total, 2) if total else 0.0
    return {
        "sessions": sessions,
        "dropped_duplicates": dropped,
        "concurrency": len(active) if since_dt else None,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(prog="burn_ledger.py", description="Cache-read share and post-reset concurrency.")
    parser.add_argument("--dir", default=str(DEFAULT_DIR), help="transcript folder (default: ~/.claude/projects)")
    parser.add_argument("--since", default=None, help="reset time, ISO 8601, e.g. 2026-10-24T10:00:00Z")
    parser.add_argument("--window", type=int, default=30, help="minutes after --since (default 30)")
    args = parser.parse_args(argv)
    if args.since and _parse_ts(args.since) is None:
        print("since: ERROR (not an ISO 8601 time)")
        return 2
    result = summarize(args.dir, args.since, args.window)
    print(f"sessions: {len(result['sessions'])}  duplicates dropped: {result['dropped_duplicates']}")
    for session in sorted(result["sessions"]):
        row = result["sessions"][session]
        print(f"{session}  project={row['project'] or '-'} input={row['input']} output={row['output']} cache_create={row['cache_create']} "
              f"cache_read={row['cache_read']} cache_read_share={row['cache_read_share']:.2f}")
    if args.since:
        print(f"concurrency: {result['concurrency']} sessions with a record in {args.window} min after {args.since}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
