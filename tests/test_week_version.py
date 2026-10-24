import json
import os
import sys
import tempfile
import unittest
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import version_watch  # noqa: E402
import week_ledger  # noqa: E402


def write(root, project, session, records):
    d = os.path.join(root, project)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, session + ".jsonl"), "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps({"sessionId": session, **r}) + "\n")


def usage(ts, mid, model="claude-opus-5-5", inp=10, out=5, cc=0, cr=0, req=None):
    return {"type": "assistant", "timestamp": ts, "requestId": req or f"req_{mid}",
            "message": {"id": mid, "model": model, "usage": {"input_tokens": inp, "output_tokens": out,
                                                             "cache_creation_input_tokens": cc, "cache_read_input_tokens": cr}}}


def tool(ts, tid, version, error=False):
    return [{"type": "assistant", "timestamp": ts, "version": version,
             "message": {"content": [{"type": "tool_use", "id": tid, "name": "Bash", "input": {"command": "x"}}]}},
            {"type": "user", "timestamp": ts, "version": version,
             "message": {"content": [{"type": "tool_result", "tool_use_id": tid, "is_error": error, "content": "boom" if error else "ok"}]}}]


class WeekLedger(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        r = self.tmp.name
        write(r, "p", "a", [usage("2026-10-21T10:00:00Z", "m1", inp=100, out=0),
                            usage("2026-10-21T10:00:01Z", "m1", inp=100, out=0),          # streamed copy
                            usage("2026-10-22T10:00:00Z", "m2", inp=200, out=0)])
        write(r, "p", "b", [usage("2026-10-23T10:00:00Z", "m3", model="claude-haiku-5-5", inp=100, out=0, cr=900),
                            usage("2026-10-24T09:00:00Z", "m4", inp=50, out=50, cr=1900)])
        write(r, "q", "c", [usage("2026-10-10T10:00:00Z", "m5", inp=999, out=0)])                   # outside 7 days
        write(r, "q", "d", [usage("2026-10-22T11:00:00Z", "m6", inp=0, out=0, cr=50)])              # share 1.0, few tokens

    def tearDown(self):
        self.tmp.cleanup()

    def test_days_models_dedupe_and_window(self):
        s = week_ledger.summarize(self.tmp.name, days=7, today=date(2026, 10, 24))
        self.assertEqual(sorted(s["days"]), ["2026-10-21", "2026-10-22", "2026-10-23", "2026-10-24"])
        self.assertEqual(s["days"]["2026-10-21"]["total"], 100)          # the streamed copy counted once
        self.assertEqual(s["days"]["2026-10-23"]["by_model"], {"claude-haiku-5-5": 1000})
        self.assertEqual(s["days"]["2026-10-24"]["sessions"], 1)
        self.assertNotIn("2026-10-10", s["days"])

    def test_top_cache_rereads(self):
        s = week_ledger.summarize(self.tmp.name, days=7, today=date(2026, 10, 24))
        top = s["top_rereads"]
        self.assertEqual(top[0][0], "b")
        self.assertEqual(top[0][1], 2800)
        self.assertAlmostEqual(top[0][2], 2800 / 3000, places=2)

    def test_today_against_the_usual(self):
        s = week_ledger.summarize(self.tmp.name, days=7, today=date(2026, 10, 24))
        self.assertEqual(s["today_total"], 2000)
        self.assertEqual(s["usual_median"], 250)                         # median of 100, 250, 1000
        self.assertEqual(s["ratio"], 8.0)

    def test_no_history_no_ratio(self):
        with tempfile.TemporaryDirectory() as r:
            write(r, "p", "a", [usage("2026-10-24T09:00:00Z", "m1")])
            s = week_ledger.summarize(r, days=7, today=date(2026, 10, 24))
            self.assertIsNone(s["ratio"])

    def test_cli_prints_numbers_only(self):
        import io
        from contextlib import redirect_stdout
        out = io.StringIO()
        with redirect_stdout(out):
            code = week_ledger.main(["--dir", self.tmp.name, "--days", "7", "--today", "2026-10-24"])
        self.assertEqual(code, 0)
        text = out.getvalue()
        self.assertIn("2026-10-24", text)
        self.assertIn("x8.0", text)


class VersionWatch(unittest.TestCase):
    def test_a_version_change_mid_session_with_errors_before_and_after(self):
        with tempfile.TemporaryDirectory() as r:
            recs = (tool("2026-10-24T09:00:00Z", "t0", "2.1.300", error=True)        # 70 min before: outside window
                    + tool("2026-10-24T09:50:00Z", "t1", "2.1.300", error=True)
                    + tool("2026-10-24T09:55:00Z", "t2", "2.1.300")
                    + tool("2026-10-24T10:10:00Z", "t3", "2.1.310", error=True)
                    + tool("2026-10-24T10:20:00Z", "t4", "2.1.310", error=True)
                    + tool("2026-10-24T10:25:00Z", "t5", "2.1.310", error=True)
                    + tool("2026-10-24T11:30:00Z", "t6", "2.1.310", error=True))      # after the window
            write(r, "p", "s1", recs)
            write(r, "p", "s2", tool("2026-10-24T10:00:00Z", "u1", "2.1.310"))
            ch = version_watch.scan(r, window_min=30)
            self.assertEqual(len(ch), 1)
            c = ch[0]
            self.assertEqual((c["session"], c["from"], c["to"]), ("s1", "2.1.300", "2.1.310"))
            self.assertEqual(c["at"], "2026-10-24T10:10:00Z")
            self.assertEqual((c["errors_before"], c["errors_after"]), (1, 3))

    def test_records_out_of_order_in_the_file(self):
        with tempfile.TemporaryDirectory() as r:
            write(r, "p", "s", tool("2026-10-24T10:10:00Z", "b", "2.1.310") + tool("2026-10-24T09:50:00Z", "a", "2.1.300"))
            ch = version_watch.scan(r)
            self.assertEqual([(c["from"], c["to"], c["at"]) for c in ch], [("2.1.300", "2.1.310", "2026-10-24T10:10:00Z")])

    def test_several_changes_and_records_without_version(self):
        with tempfile.TemporaryDirectory() as r:
            recs = (tool("2026-10-24T09:00:00Z", "a", "1.0.0") + [{"type": "summary", "timestamp": "2026-10-24T09:01:00Z"}]
                    + tool("2026-10-24T09:10:00Z", "b", "1.0.1") + tool("2026-10-24T09:20:00Z", "c", "1.0.2"))
            write(r, "p", "s", recs)
            self.assertEqual([(c["from"], c["to"]) for c in version_watch.scan(r)], [("1.0.0", "1.0.1"), ("1.0.1", "1.0.2")])

    def test_cli(self):
        import io
        from contextlib import redirect_stdout
        with tempfile.TemporaryDirectory() as r:
            write(r, "p", "s1", tool("2026-10-24T09:50:00Z", "t1", "2.1.300") + tool("2026-10-24T10:10:00Z", "t2", "2.1.310", True))
            out = io.StringIO()
            with redirect_stdout(out):
                self.assertEqual(version_watch.main(["--dir", r]), 0)
            self.assertIn("2.1.300 -> 2.1.310", out.getvalue())
            self.assertIn("errors 0 before / 1 after", out.getvalue())


if __name__ == "__main__":
    unittest.main()
