"""version-watch: did Claude Code update itself in the middle of your session, and did things break after?

"Your background Claude Code update blew up my work." Every transcript record carries the Claude Code `version`
that wrote it. version-watch finds each session where it changed mid-way, when, from what to what, and counts failed
tool calls in the N minutes before and after the change (failure = is_error, or an `Exit code N` line with N != 0,
the same rule as error-tail). A count, not a cause: it tells you where to look.
"""
import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path

from cc_jsonl import iter_records
from error_tail import _failed, _text

DEFAULT_DIR = Path.home() / ".claude" / "projects"


def _ts(text):
    try:
        return datetime.fromisoformat(str(text).replace("Z", "+00:00"))
    except ValueError:
        return None


def scan(root, window_min=30):
    per = {}
    for session, _project, rec in iter_records(root):
        t = _ts(rec.get("timestamp"))
        if t is None:
            continue
        failed = 0
        content = (rec.get("message") or {}).get("content")
        if isinstance(content, list):
            failed = sum(1 for b in content if isinstance(b, dict) and b.get("type") == "tool_result"
                         and _failed(b, _text(b.get("content"))))
        per.setdefault(session, []).append((t, rec.get("timestamp"), rec.get("version"), failed))
    w = timedelta(minutes=window_min)
    changes = []
    for session, rows in per.items():
        rows.sort(key=lambda r: r[0])
        prev = None
        for t, raw, ver, _ in rows:
            if not ver:
                continue
            if prev and ver != prev:
                changes.append({"session": session, "at": raw, "from": prev, "to": ver,
                                "errors_before": sum(f for tt, _, _, f in rows if t - w <= tt < t),
                                "errors_after": sum(f for tt, _, _, f in rows if t <= tt < t + w)})
            prev = ver
    return sorted(changes, key=lambda c: c["at"])


def main(argv=None):
    p = argparse.ArgumentParser(prog="version_watch.py", description="Claude Code version changes inside sessions.")
    p.add_argument("--dir", default=str(DEFAULT_DIR), help="transcript folder (default: ~/.claude/projects)")
    p.add_argument("--window", type=int, default=30, help="minutes before/after a change to count errors (default 30)")
    a = p.parse_args(argv)
    ch = scan(a.dir, a.window)
    if not ch:
        print("no Claude Code version change inside any session")
        return 0
    for c in ch:
        print(f"{c['at']}  {c['session']}  {c['from']} -> {c['to']}  "
              f"errors {c['errors_before']} before / {c['errors_after']} after ({a.window} min)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
