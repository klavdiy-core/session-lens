"""burn-ledger --by-entry: the same work through the Agents SDK and through interactive Claude Code, side by side.
Complaints (25.10): x.com/theo/status/2114166439813017873 (an Anthropic-side bug: the SDK burns the 5-hour window
faster), x.com/jax_wu/status/2114176072526844353 (a window in 30 minutes through T3 Code vs ~16 %/h in the CLI)."""
import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import burn_ledger as bl  # noqa: E402


def rec(sid, entry, msg, inp, out, cread, ccreate=0):
    return json.dumps({"type": "assistant", "sessionId": sid, "entrypoint": entry, "requestId": "r" + msg,
                       "timestamp": "2026-10-25T10:00:00Z",
                       "message": {"id": msg, "usage": {"input_tokens": inp, "output_tokens": out,
                                                        "cache_read_input_tokens": cread,
                                                        "cache_creation_input_tokens": ccreate}}})


class ByEntry(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        p = self.root / "proj"
        p.mkdir()
        (p / "a.jsonl").write_text("\n".join([rec("a", "cli", "m1", 10, 100, 20000),
                                              rec("a", "cli", "m2", 10, 100, 22000)]) + "\n", encoding="utf-8")
        (p / "b.jsonl").write_text("\n".join([rec("b", "sdk-cli", "m3", 10, 100, 60000, 30000),
                                              rec("b", "sdk-cli", "m3", 10, 100, 60000, 30000),     # a streamed copy
                                              rec("b", "sdk-cli", "m4", 10, 100, 64000)]) + "\n", encoding="utf-8")
        (p / "c.jsonl").write_text(json.dumps({"type": "assistant", "sessionId": "c", "requestId": "r5",
                                               "message": {"id": "m5", "usage": {"output_tokens": 50}}}) + "\n",
                                   encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_each_entry_point_gets_its_totals_per_reply(self):
        rows = bl.by_entry(bl.summarize(self.root))
        self.assertEqual(set(rows), {"cli", "sdk-cli", "(unknown)"})
        self.assertEqual(rows["cli"]["sessions"], 1)
        self.assertEqual(rows["cli"]["replies"], 2)
        self.assertEqual(rows["sdk-cli"]["replies"], 2)                 # the streamed copy counts once
        self.assertEqual(rows["cli"]["cache_read_per_reply"], 21000)
        self.assertEqual(rows["sdk-cli"]["cache_read_per_reply"], 62000)
        self.assertEqual(rows["sdk-cli"]["tokens_per_output_token"], round((20 + 200 + 124000 + 30000) / 200, 1))

    def test_the_cli_prints_the_comparison_and_says_what_it_is_not(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = bl.main(["--dir", str(self.root), "--by-entry"])
        text = out.getvalue()
        self.assertEqual(code, 0)
        self.assertIn("sdk-cli", text)
        self.assertIn("3.0x", text)                                     # 62000 / 21000 = 2.95 cache read per reply
        self.assertIn("not a share of any limit", text)


if __name__ == "__main__":
    unittest.main()
