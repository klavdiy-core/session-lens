"""Unit tests for burn-ledger. All transcripts are synthetic, written by hand into a temp folder."""
import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import burn_ledger as bl  # noqa: E402


def line(msg_id, req_id, ts, inp=0, out=0, cache_create=0, cache_read=0, sidechain=False, sid=None):
    rec = {
        "type": "assistant",
        "requestId": req_id,
        "timestamp": ts,
        "isSidechain": sidechain,
        "message": {
            "id": msg_id,
            "usage": {
                "input_tokens": inp,
                "output_tokens": out,
                "cache_creation_input_tokens": cache_create,
                "cache_read_input_tokens": cache_read,
            },
        },
    }
    if sid:
        rec["sessionId"] = sid
    return json.dumps(rec)


class BurnLedgerTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def _write(self, rel, lines):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def test_same_message_id_and_request_id_counts_once(self):
        # Streaming writes the same assistant message several times: must not double the sum.
        self._write("s1.jsonl", [
            line("msg_1", "req_1", "2026-10-24T10:00:00Z", inp=10, out=5),
            line("msg_1", "req_1", "2026-10-24T10:00:01Z", inp=10, out=5),
        ])
        result = bl.summarize(self.root)
        self.assertEqual(result["sessions"]["s1"]["input"], 10)
        self.assertEqual(result["sessions"]["s1"]["output"], 5)

    def test_different_message_ids_are_both_counted(self):
        self._write("s1.jsonl", [
            line("msg_1", "req_1", "2026-10-24T10:00:00Z", inp=10),
            line("msg_2", "req_2", "2026-10-24T10:00:05Z", inp=7),
        ])
        result = bl.summarize(self.root)
        self.assertEqual(result["sessions"]["s1"]["input"], 17)

    def test_sidechain_file_is_counted_for_its_session(self):
        self._write("s1.jsonl", [line("msg_1", "req_1", "2026-10-24T10:00:00Z", inp=10)])
        self._write("s1/subagents/agent-a.jsonl",
                    [line("msg_9", "req_9", "2026-10-24T10:01:00Z", inp=40, sidechain=True)])
        result = bl.summarize(self.root)
        self.assertEqual(result["sessions"]["s1"]["input"], 50)

    def test_concurrency_counts_sessions_active_in_window_after_since(self):
        since = "2026-10-24T10:00:00Z"
        self._write("a.jsonl", [line("m1", "r1", "2026-10-24T10:05:00Z", inp=1)])
        self._write("b.jsonl", [line("m2", "r2", "2026-10-24T10:10:00Z", inp=1)])
        self._write("c.jsonl", [line("m3", "r3", "2026-10-24T10:20:00Z", inp=1)])
        result = bl.summarize(self.root, since=since, window_min=30)
        self.assertEqual(result["concurrency"], 3)

    def test_session_outside_window_is_not_counted(self):
        since = "2026-10-24T10:00:00Z"
        self._write("a.jsonl", [line("m1", "r1", "2026-10-24T10:05:00Z", inp=1)])
        self._write("b.jsonl", [line("m2", "r2", "2026-10-24T10:45:00Z", inp=1)])  # after the 30 min window
        result = bl.summarize(self.root, since=since, window_min=30)
        self.assertEqual(result["concurrency"], 1)

    def test_the_records_session_id_wins_over_the_file_name(self):
        # reviewer: the fixtures named files after their sessionId, so "session = file name" stayed green
        self._write("C--proj-a/renamed.jsonl", [line("m1", "r1", "2026-10-24T10:05:00Z", inp=7, sid="s9")])
        result = bl.summarize(self.root)
        self.assertEqual(sorted(result["sessions"]), ["s9"])

    def test_two_sessions_in_one_project_folder_are_two_sessions(self):
        # real layout: <project>/<session-id>.jsonl, several sessions per project folder
        self._write("C--proj-a/s1.jsonl", [line("m1", "r1", "2026-10-24T10:05:00Z", inp=10, sid="s1")])
        self._write("C--proj-a/s2.jsonl", [line("m2", "r2", "2026-10-24T10:07:00Z", inp=20, sid="s2")])
        result = bl.summarize(self.root, since="2026-10-24T10:00:00Z")
        self.assertEqual(sorted(result["sessions"]), ["s1", "s2"])
        self.assertEqual(result["sessions"]["s2"]["input"], 20)
        self.assertEqual(result["concurrency"], 2)

    def test_cache_read_share_is_fraction_of_all_input_side_tokens(self):
        self._write("s1.jsonl", [line("m1", "r1", "2026-10-24T10:00:00Z", inp=10, out=10, cache_read=80)])
        result = bl.summarize(self.root)
        self.assertAlmostEqual(result["sessions"]["s1"]["cache_read_share"], 0.8)

    def test_output_never_has_percent_of_allowance(self):
        self._write("s1.jsonl", [line("m1", "r1", "2026-10-24T10:00:00Z", inp=10, cache_read=90)])
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            bl.main(["--dir", str(self.root), "--since", "2026-10-24T10:00:00Z"])
        out = buf.getvalue()
        self.assertNotIn("% of", out)
        self.assertNotIn("%", out)


if __name__ == "__main__":
    unittest.main()
