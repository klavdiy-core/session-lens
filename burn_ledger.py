"""burn-ledger: two numbers that `ccusage` does not give.

1. cache_read_share per session: how much of the context a session re-reads from cache (0.00 .. 1.00).
2. concurrency after a limit reset: how many sessions had at least one record in the first N minutes after --since.

Reads Claude Code transcripts (--dir, default ~/.claude/projects). Dedupes streamed copies of one assistant message
by (message.id, requestId). Counts sub-agent (sidechain) files. Prints numbers only, never prompt or output content,
and never a share of any allowance.
"""
import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cc_jsonl import iter_records, parse_ts, unique_usage

DEFAULT_DIR = Path.home() / ".claude" / "projects"
FIELDS = ("input", "output", "cache_create", "cache_read")


def _parse_ts(text):
    return parse_ts(text)          # the shared reading: a time without a zone is UTC


def summarize(root, since=None, window_min=30):
    since_dt = _parse_ts(since) if since else None
    end_dt = since_dt + timedelta(minutes=window_min) if since_dt else None
    active, sessions, entry = set(), {}, {}

    def records():
        for session, project, rec in iter_records(root):
            ts = _parse_ts(rec.get("timestamp"))
            if since_dt and ts and since_dt <= ts < end_dt:
                active.add(session)
            if rec.get("entrypoint") and session not in entry:
                entry[session] = str(rec["entrypoint"])        # cli, sdk-cli, sdk-ts, ... as Claude Code writes it
            yield session, project, rec

    rows, dropped = unique_usage(records())
    for session, project, rec in rows:
        usage = rec["message"]["usage"]
        row = sessions.setdefault(session, dict.fromkeys(FIELDS, 0))
        row.setdefault("project", project)
        row["replies"] = row.get("replies", 0) + 1
        row["input"] += int(usage.get("input_tokens") or 0)
        row["output"] += int(usage.get("output_tokens") or 0)
        row["cache_create"] += int(usage.get("cache_creation_input_tokens") or 0)
        row["cache_read"] += int(usage.get("cache_read_input_tokens") or 0)
    for session, row in sessions.items():
        row["entrypoint"] = entry.get(session, "(unknown)")
        total = sum(row[f] for f in FIELDS)
        row["cache_read_share"] = round(row["cache_read"] / total, 2) if total else 0.0
    return {
        "sessions": sessions,
        "dropped_duplicates": dropped,
        "concurrency": len(active) if since_dt else None,
    }


def by_entry(result):
    """The sessions grouped by how they were started (the transcript's entrypoint): the same kind of work through the
    Agents SDK or `claude -p` (sdk-*) next to interactive Claude Code (cli). Per reply = per unique assistant message.
    Tokens and their ratios only: how a plan's limit weighs them is not public, so no share of a limit is derived."""
    out = {}
    for row in result["sessions"].values():
        g = out.setdefault(row["entrypoint"], {**dict.fromkeys(FIELDS, 0), "sessions": 0, "replies": 0})
        g["sessions"] += 1
        g["replies"] += row.get("replies", 0)
        for f in FIELDS:
            g[f] += row[f]
    for g in out.values():
        total = sum(g[f] for f in FIELDS)
        g["total"] = total
        g["cache_read_per_reply"] = round(g["cache_read"] / g["replies"]) if g["replies"] else 0
        g["tokens_per_reply"] = round(total / g["replies"]) if g["replies"] else 0
        g["tokens_per_output_token"] = round(total / g["output"], 1) if g["output"] else None
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(prog="burn_ledger.py", description="Cache-read share and post-reset concurrency.")
    parser.add_argument("--dir", default=str(DEFAULT_DIR), help="transcript folder (default: ~/.claude/projects)")
    parser.add_argument("--since", default=None, help="reset time, ISO 8601, e.g. 2026-10-24T10:00:00Z (no zone = UTC)")
    parser.add_argument("--window", type=int, default=30, help="minutes after --since (default 30)")
    parser.add_argument("--by-entry", action="store_true", help="group by entry point: SDK / claude -p vs interactive")
    args = parser.parse_args(argv)
    if args.since and _parse_ts(args.since) is None:
        print("since: ERROR (not an ISO 8601 time)")
        return 2
    try:
        result = summarize(args.dir, args.since, args.window)
    except FileNotFoundError as e:
        print(f"dir: ERROR ({e})")
        return 2
    if args.by_entry:
        rows = by_entry(result)
        base = rows.get("cli")
        print("entry       sessions  replies  tokens/reply  cache_read/reply  tokens/output_token")
        for name in sorted(rows, key=lambda n: (n != "cli", n)):
            g = rows[name]
            vs = ""
            if base and name != "cli" and base["cache_read_per_reply"]:
                vs = f"  ({g['cache_read_per_reply'] / base['cache_read_per_reply']:.1f}x the cli's cache read per reply)"
            print(f"{name:<11} {g['sessions']:>8} {g['replies']:>8} {g['tokens_per_reply']:>13} "
                  f"{g['cache_read_per_reply']:>17} {g['tokens_per_output_token']!s:>20}{vs}")
        print("tokens as the transcripts record them; not a share of any limit (how a plan weighs them is not public)")
        return 0
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
