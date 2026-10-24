"""week-ledger: your week of Claude Code, by day and by model, and today against the usual.

"People are burning their weekly allowance in 1-2 days. Same workflows." Before arguing about it, look at your own
week: tokens per day (dates in UTC), split by model, how many sessions, which sessions re-read the most cached
context, and today's total against the median of the earlier days that had any use.

Same reading rules as burn-ledger: streamed copies of one message (same message.id + requestId) count once.
Raw tokens, not priced; never a share of any allowance. Prints numbers only.
"""
import argparse
import statistics
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

from cc_jsonl import iter_records

DEFAULT_DIR = Path.home() / ".claude" / "projects"


def _day(ts):
    try:
        return datetime.fromisoformat(str(ts).replace("Z", "+00:00")).date()
    except ValueError:
        return None


def summarize(root, days=7, today=None, top=5):
    today = today or datetime.utcnow().date()
    first = today - timedelta(days=days - 1)
    seen, out, sess = set(), {}, {}
    for session, _project, rec in iter_records(root):
        msg = rec.get("message") or {}
        u = msg.get("usage")
        d = _day(rec.get("timestamp"))
        if not isinstance(u, dict) or d is None or not (first <= d <= today):
            continue
        key = (msg.get("id"), rec.get("requestId"))
        if key[0] and key[1]:
            if key in seen:
                continue
            seen.add(key)
        cr = int(u.get("cache_read_input_tokens") or 0)
        total = (int(u.get("input_tokens") or 0) + int(u.get("output_tokens") or 0)
                 + int(u.get("cache_creation_input_tokens") or 0) + cr)
        row = out.setdefault(d.isoformat(), {"total": 0, "cache_read": 0, "by_model": {}, "_sessions": set()})
        row["total"] += total
        row["cache_read"] += cr
        model = msg.get("model") or "?"
        row["by_model"][model] = row["by_model"].get(model, 0) + total
        row["_sessions"].add(session)
        s = sess.setdefault(session, [0, 0])
        s[0] += cr
        s[1] += total
    for row in out.values():
        row["sessions"] = len(row.pop("_sessions"))
    rereads = sorted(((k, v[0], v[0] / v[1] if v[1] else 0.0) for k, v in sess.items()), key=lambda x: -x[1])[:top]
    today_total = out.get(today.isoformat(), {}).get("total", 0)
    earlier = [r["total"] for d, r in out.items() if d < today.isoformat() and r["total"] > 0]
    median = statistics.median(earlier) if earlier else None
    return {"days": out, "top_rereads": rereads, "today": today.isoformat(), "today_total": today_total,
            "usual_median": median, "usual_days": len(earlier),
            "ratio": round(today_total / median, 1) if median else None}


def main(argv=None):
    p = argparse.ArgumentParser(prog="week_ledger.py", description="Tokens per day and model; today vs the usual.")
    p.add_argument("--dir", default=str(DEFAULT_DIR), help="transcript folder (default: ~/.claude/projects)")
    p.add_argument("--days", type=int, default=7)
    p.add_argument("--today", default=None, help="YYYY-MM-DD (UTC), default: today")
    a = p.parse_args(argv)
    today = date.fromisoformat(a.today) if a.today else None
    s = summarize(a.dir, a.days, today)
    print(f"day (UTC)    tokens        cache_read    sessions  by model")
    for d in sorted(s["days"]):
        r = s["days"][d]
        models = ", ".join(f"{m} {n}" for m, n in sorted(r["by_model"].items(), key=lambda x: -x[1]))
        print(f"{d}  {r['total']:>12}  {r['cache_read']:>12}  {r['sessions']:>8}  {models}")
    if s["ratio"] is not None:
        print(f"today {s['today']}: {s['today_total']} tokens = x{s['ratio']} the median of {s['usual_days']} earlier "
              f"day(s) ({s['usual_median']:g})")
    else:
        print(f"today {s['today']}: {s['today_total']} tokens (no earlier days to compare with)")
    print("most cache re-read (session, cache_read tokens, share of its tokens):")
    for k, cr, share in s["top_rereads"]:
        print(f"  {k}  {cr}  {share:.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
