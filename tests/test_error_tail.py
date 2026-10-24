"""Unit tests for error-tail. Synthetic transcripts only, written by hand into a temp folder."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import error_tail as et  # noqa: E402

TRACEBACK = (
    "Traceback (most recent call last):\n"
    '  File "run.py", line 4, in <module>\n'
    "    main()\n"
    '  File "run.py", line 2, in main\n'
    "    raise ValueError('x')\n"
    "ValueError: x"
)


def call(tool_id, name, text, is_error=False, ts="2026-10-24T10:00:00Z", sid=None):
    """Return two JSONL lines: the tool call and its result."""
    use = {"type": "assistant", "timestamp": ts, "sessionId": sid,
           "message": {"content": [{"type": "tool_use", "id": tool_id, "name": name, "input": {}}]}}
    res = {"type": "user", "timestamp": ts, "sessionId": sid,
           "message": {"content": [{"type": "tool_result", "tool_use_id": tool_id,
                                    "is_error": is_error, "content": text}]}}
    return [json.dumps(use), json.dumps(res)]


class ErrorTailTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.path = self.root / "s1.jsonl"

    def _write(self, lines, path=None):
        (path or self.path).write_text("\n".join(lines) + "\n", encoding="utf-8")

    def test_traceback_gives_last_line(self):
        self.assertEqual(et.first_error_line(TRACEBACK), "ValueError: x")

    def test_compiler_error_gives_first_error_line(self):
        text = "src/a.c:3: error: expected ';' before '}'\nsrc/a.c:9: error: unknown type"
        self.assertEqual(et.first_error_line(text), "src/a.c:3: error: expected ';' before '}'")

    def test_bash_exit_code_is_caught(self):
        self._write(call("t1", "Bash", "Exit code 2\nno such file", is_error=False))
        rows = et.last_errors(self.root)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][1], "Bash")
        self.assertIn("Exit code 2", rows[0][2])

    def test_successful_call_is_not_listed(self):
        self._write(call("t1", "Bash", "Exit code 0\nall good", is_error=False)
                    + call("t2", "Read", "file contents here", is_error=False))
        self.assertEqual(et.last_errors(self.root), [])

    def test_session_flag_picks_that_session_only(self):
        # real layout: <project>/<session-id>.jsonl, two sessions in one folder
        folder = self.root / "C--proj-a"
        folder.mkdir()
        self._write(call("t1", "Bash", "Exit code 1\nboom one", sid="s1"), folder / "s1.jsonl")
        self._write(call("t2", "Bash", "Exit code 2\nboom two", sid="s2"), folder / "s2.jsonl")
        rows = et.last_errors(self.root, session="s2")
        self.assertEqual(len(rows), 1)
        self.assertIn("Exit code 2", rows[0][2])

    def test_exit_code_line_is_followed_by_last_nonempty_output_line(self):
        text = "Exit code 1\nstarting build\nbuilding module x\nbuild stopped at step 3\n"
        self.assertEqual(et.first_error_line(text), "Exit code 1: build stopped at step 3")


if __name__ == "__main__":
    unittest.main()
