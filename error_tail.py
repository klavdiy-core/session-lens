"""error-tail: the last few tool errors of one Claude Code session, one line each.

Output: time, tool name, and ONE line of the error. Rule for the line:
- Python traceback -> its last line (ValueError: x);
- compiler / `error:` output -> the first line that says `error:`;
- Bash failure (is_error, or a `Exit code N` line with N != 0) -> that `Exit code N` line.
Reads transcripts through cc_jsonl.py (shared with burn-ledger). Prints tool output lines only, never more.
"""
import argparse
import re
import sys
from pathlib import Path

from cc_jsonl import iter_records

DEFAULT_DIR = Path.home() / ".claude" / "projects"
ERROR_WORD = re.compile(r"error:", re.IGNORECASE)
EXIT_LINE = re.compile(r"^Exit code (\d+)$")
DETAIL_WORD = re.compile(r"error|ERR!|fatal", re.IGNORECASE)


def first_error_line(text):
    lines = [ln.strip() for ln in str(text).splitlines() if ln.strip()]
    if not lines:
        return ""
    if any(ln.startswith("Traceback (most recent call last)") for ln in lines):
        return lines[-1]
    for ln in lines:
        if ERROR_WORD.search(ln):
            return ln
    for i, ln in enumerate(lines):
        if EXIT_LINE.match(ln):
            body = lines[i + 1:]
            detail = next((b for b in body if DETAIL_WORD.search(b)), None) or (body[-1] if body else None)
            return f"{ln}: {detail}" if detail else ln
    return lines[0]


def _text(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(str(b.get("text", "")) for b in content if isinstance(b, dict))
    return ""


def _failed(block, text):
    if block.get("is_error") is True:
        return True
    for ln in text.splitlines():
        match = EXIT_LINE.match(ln.strip())
        if match and int(match.group(1)) != 0:
            return True
    return False


def _collect(root):
    """One pass over every session: failed tool calls as (session, ts, tool, line), and last time per session."""
    names, rows, last = {}, [], {}
    for session, _project, rec in iter_records(root):
        ts = rec.get("timestamp") or ""
        last[session] = max(last.get(session, ""), ts)
        content = (rec.get("message") or {}).get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "tool_use":
                names[(session, block.get("id"))] = block.get("name", "?")
            elif block.get("type") == "tool_result":
                text = _text(block.get("content"))
                if _failed(block, text):
                    tool = names.get((session, block.get("tool_use_id")), "?")
                    rows.append((session, ts, tool, first_error_line(text)))
    return rows, last


def last_errors(root, session=None, n=5):
    """Return [(timestamp, tool, error line)] for the last n failed tool calls of one session.

    session=None picks the session with the latest record under root.
    """
    rows, last = _collect(root)
    if session is None:
        if not last:
            return []
        session = max(last, key=last.get)
    mine = [(ts, tool, line) for s, ts, tool, line in rows if s == session]
    return mine[max(0, len(mine) - n):]


def main(argv=None):
    parser = argparse.ArgumentParser(prog="error_tail.py", description="Last tool errors of one session.")
    parser.add_argument("--dir", default=str(DEFAULT_DIR), help="transcript folder (default: ~/.claude/projects)")
    parser.add_argument("--session", default=None, help="session id (default: the most recently written session)")
    parser.add_argument("-n", type=int, default=5, help="how many errors (default 5)")
    args = parser.parse_args(argv)
    rows = last_errors(args.dir, args.session, args.n)
    _, last = _collect(args.dir)
    session = args.session or (max(last, key=last.get) if last else None)
    if session is None or session not in last:
        print("session: NOT FOUND")
        return 3
    print(f"session: {session}  errors: {len(rows)}")
    for ts, tool, line in rows:
        print(f"{ts} {tool} {line}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
