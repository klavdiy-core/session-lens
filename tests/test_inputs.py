"""Found by an independent tester on a clean clone, 24.10: bad input must fail clearly, never look like an empty week."""
import contextlib
import io
import os
import sys
import tempfile
import unittest
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
import burn_ledger  # noqa: E402
import error_tail  # noqa: E402
import version_watch  # noqa: E402
import week_ledger  # noqa: E402
from test_week_version import usage, write  # noqa: E402


def run(main, argv):
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        code = main(argv)
    return code, out.getvalue()


class Inputs(unittest.TestCase):
    def test_a_missing_dir_is_an_error_not_an_empty_success(self):
        missing = os.path.join(tempfile.gettempdir(), "no_such_session_lens_dir")
        for mod in (burn_ledger, week_ledger, error_tail, version_watch):
            code, text = run(mod.main, ["--dir", missing])
            self.assertEqual(code, 2, mod.__name__)
            self.assertIn("not found", text, mod.__name__)

    def test_since_without_a_timezone_is_read_as_utc(self):
        with tempfile.TemporaryDirectory() as d:
            write(d, "p", "a", [usage("2026-10-24T10:05:00Z", "m1")])
            code, text = run(burn_ledger.main, ["--dir", d, "--since", "2026-10-24T10:00:00"])
        self.assertEqual(code, 0, text)
        self.assertIn("concurrency: 1", text)


class StreamedCopies(unittest.TestCase):
    """Measured 24.10 on ~16,000 real messages (Claude Code 2.1.300-2.1.310): streamed copies carried the same
    output_tokens every time. If a version ever writes a growing count, the largest copy is the true one."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        write(self.tmp.name, "p", "a", [usage("2026-10-21T10:00:00Z", "m1", out=1),
                                        usage("2026-10-21T10:00:01Z", "m1", out=40)])

    def tearDown(self):
        self.tmp.cleanup()

    def test_burn_ledger_counts_the_largest_copy_once(self):
        s = burn_ledger.summarize(self.tmp.name)
        self.assertEqual(s["sessions"]["a"]["output"], 40)
        self.assertEqual(s["dropped_duplicates"], 1)

    def test_week_ledger_counts_the_largest_copy_once(self):
        s = week_ledger.summarize(self.tmp.name, days=7, today=date(2026, 10, 21))
        self.assertEqual(s["days"]["2026-10-21"]["total"], 10 + 40)


if __name__ == "__main__":
    unittest.main()
