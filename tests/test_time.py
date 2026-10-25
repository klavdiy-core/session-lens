"""Found by an outside practice re-grade, 25.10: the four tools read timestamps three different ways."""
import os
import sys
import tempfile
import unittest
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
import burn_ledger  # noqa: E402
import cc_jsonl  # noqa: E402
import version_watch  # noqa: E402
import week_ledger  # noqa: E402
from test_inputs import run  # noqa: E402
from test_week_version import tool, usage, write  # noqa: E402


class Time(unittest.TestCase):
    def test_one_reading_of_time_for_every_tool(self):
        self.assertEqual(cc_jsonl.parse_ts("2026-10-25T01:30:00+03:00").isoformat(), "2026-10-24T22:30:00+00:00")
        self.assertEqual(cc_jsonl.parse_ts("2026-10-24T22:30:00").isoformat(), "2026-10-24T22:30:00+00:00")  # naive = UTC
        self.assertIsNone(cc_jsonl.parse_ts("yesterday"))
        self.assertIsNone(cc_jsonl.parse_ts(None))

    def test_the_week_is_bucketed_by_utc_day(self):
        with tempfile.TemporaryDirectory() as d:
            write(d, "p", "a", [usage("2026-10-25T01:30:00+03:00", "m1", inp=100, out=0)])   # 22:30Z on the 24th
            s = week_ledger.summarize(d, days=3, today=date(2026, 10, 25))
        self.assertEqual(list(s["days"]), ["2026-10-24"])

    def test_a_session_mixing_zoned_and_naive_times_does_not_crash(self):
        with tempfile.TemporaryDirectory() as d:
            write(d, "p", "a", tool("2026-10-24T10:00:00Z", "t1", "2.1.300")
                  + tool("2026-10-24T10:05:00", "t2", "2.1.310", error=True))
            changes = version_watch.scan(d)
        self.assertEqual([(c["from"], c["to"]) for c in changes], [("2.1.300", "2.1.310")])

    def test_a_bad_today_or_days_is_a_clean_error(self):
        with tempfile.TemporaryDirectory() as d:
            write(d, "p", "a", [usage("2026-10-24T10:00:00Z", "m1")])
            for argv in (["--today", "2026-13-40"], ["--days", "0"], ["--days", "-3"]):
                code, text = run(week_ledger.main, ["--dir", d] + argv)
                self.assertEqual(code, 2, (argv, text))
                self.assertNotIn("Traceback", text)

    def test_copies_without_a_request_id_count_once(self):
        def copy(n):
            r = usage("2026-10-24T10:00:0%dZ" % n, "m1", inp=11, out=0)
            del r["requestId"]
            return r
        with tempfile.TemporaryDirectory() as d:
            write(d, "p", "a", [copy(0), copy(1), copy(2), copy(3)])
            s = week_ledger.summarize(d, days=1, today=date(2026, 10, 24))
            code, text = run(burn_ledger.main, ["--dir", d])
        self.assertEqual(s["days"]["2026-10-24"]["total"], 11)
        self.assertIn("duplicates dropped: 3", text)


if __name__ == "__main__":
    unittest.main()
