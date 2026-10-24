"""Write the synthetic examples (examples/week, examples/version) and render examples/week_version.png from the
REAL output of week_ledger.py and version_watch.py on them. All data here is made up.
    pip install pillow ; python examples/make_examples.py
"""
import io
import json
import os
import shutil
import sys
from contextlib import redirect_stdout

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import version_watch  # noqa: E402
import week_ledger  # noqa: E402


def write(root, session, recs):
    d = os.path.join(root, "proj")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, session + ".jsonl"), "w", encoding="utf-8") as f:
        f.write("\n".join(json.dumps({"sessionId": session, **r}) for r in recs) + "\n")


def use(ts, mid, model, inp, out, cr):
    return {"type": "assistant", "timestamp": ts, "requestId": "r" + mid,
            "message": {"id": mid, "model": model, "usage": {"input_tokens": inp, "output_tokens": out,
                                                             "cache_creation_input_tokens": 0, "cache_read_input_tokens": cr}}}


def tool(ts, tid, ver, err):
    return [{"type": "assistant", "timestamp": ts, "version": ver,
             "message": {"content": [{"type": "tool_use", "id": tid, "name": "Bash", "input": {"command": "npm test"}}]}},
            {"type": "user", "timestamp": ts, "version": ver,
             "message": {"content": [{"type": "tool_result", "tool_use_id": tid, "is_error": err, "content": "x"}]}}]


def main():
    week = os.path.join(HERE, "week")
    shutil.rmtree(week, ignore_errors=True)
    n = 0
    for day, sessions in (("18", 2), ("19", 2), ("20", 3), ("21", 2), ("22", 2), ("23", 3), ("24", 6)):
        for s in range(sessions):
            n += 1
            heavy = day == "24" and s >= 3            # three long sessions on the last day
            write(week, f"s{n:02}", [use(f"2026-10-{day}T{9 + s:02d}:00:00Z", f"m{n}a", "claude-opus-5-5", 40000, 6000,
                                         1900000 if heavy else 300000),
                                     use(f"2026-10-{day}T{9 + s:02d}:30:00Z", f"m{n}b", "claude-haiku-5-5", 8000, 2000, 50000)])
    ver = os.path.join(HERE, "version")
    shutil.rmtree(ver, ignore_errors=True)
    recs = []
    for i, (hh, mm) in enumerate(((10, 5), (10, 20), (10, 40))):
        recs += tool(f"2026-10-24T{hh}:{mm:02}:00Z", f"a{i}", "2.1.300", False)
    for i, (hh, mm) in enumerate(((11, 2), (11, 9), (11, 15), (11, 21), (11, 28))):
        recs += tool(f"2026-10-24T{hh}:{mm:02}:00Z", f"b{i}", "2.1.310", i != 1)
    write(ver, "focus-session", recs)

    out = io.StringIO()
    with redirect_stdout(out):
        print("$ python week_ledger.py --today 2026-10-24")
        week_ledger.main(["--dir", week, "--today", "2026-10-24"])
        print()
        print("$ python version_watch.py")
        version_watch.main(["--dir", ver])
    text = out.getvalue()
    print(text)
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        return
    try:
        mono = ImageFont.truetype("consola.ttf", 15)
    except OSError:
        mono = ImageFont.load_default()
    lines = ["synthetic data, real output of the tools:", ""] + text.rstrip().splitlines()
    img = Image.new("RGB", (1180, 30 + 21 * len(lines)), (24, 26, 33))
    d = ImageDraw.Draw(img)
    for i, l in enumerate(lines):
        c = (230, 200, 110) if ("x" in l and "median" in l) or "->" in l else (120, 126, 140) if l.startswith(("$", "synthetic")) else (220, 223, 228)
        d.text((18, 15 + i * 21), l, font=mono, fill=c)
    img.save(os.path.join(HERE, "week_version.png"))


if __name__ == "__main__":
    main()
