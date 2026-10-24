# session-lens

Two small readers of your Claude Code transcripts: where your usage went, and what just broke.

> RU: два маленьких инструмента поверх транскриптов Claude Code. **burn-ledger** — какая сессия съела лимит перечитыванием старого контекста и сколько сессий навалились сразу после сброса. **error-tail** — последние ошибки инструментов одной строкой, чтобы не листать всю сессию.

Standard library only, Python 3.8+. They read `~/.claude/projects/**/*.jsonl` (or `--dir`), print numbers or one line per error, and never print your prompts or Claude's answers.

## burn-ledger: where did the limit go?

"The weekly limit was gone by lunch." [ccusage](https://github.com/ryoppippi/ccusage) already shows daily, per-session and 5-hour-block usage. burn-ledger adds only the two things it doesn't:

1. **cache_read_share per session**: how much of a session's input is old context re-read from cache, 0.00 to 1.00. Every message re-sends the whole conversation; a long session shows a number near 1.
2. **concurrency after a reset**: how many sessions wrote anything in the first N minutes (default 30) after a reset time you give with `--since`. Several sessions resuming together right after a reset show up here.

```
python burn_ledger.py
python burn_ledger.py --since 2026-10-24T10:00:00Z --window 30
```

```
$ python burn_ledger.py --dir examples/burn-ledger/layout --since 2026-10-24T10:00:00Z
sessions: 2  duplicates dropped: 0
s1  project=C--proj-a input=10 output=5 cache_create=0 cache_read=40 cache_read_share=0.73
s2  project=C--proj-a input=20 output=5 cache_create=0 cache_read=0 cache_read_share=0.00
concurrency: 2 sessions with a record in 30 min after 2026-10-24T10:00:00Z
```

How it counts:
- A session is the record's `sessionId` (else the file name). Real layout is `<project>/<session id>.jsonl`, many sessions per project folder; sub-agent files in `<session>/subagents/` count to their parent.
- **Streaming writes the same assistant message several times.** Records with the same `message.id` + `requestId` count once; without that, every number would be inflated several times over.
- `cache_read_share = cache_read / (input + cache_create + cache_read + output)`.

Honest limits: raw token counts, not priced, and cache reads are not weighted the way any plan weights them. It never prints "% of your allowance": it cannot know your limit. Concurrency counts sessions that wrote in the window, not sessions busy at the same instant.

## error-tail: what broke?

An agent runs in the background; its error is buried somewhere in a long session. error-tail prints the last few tool errors of one session: time, tool, and one line.

```
python error_tail.py                        # the most recent session, last 5 errors
python error_tail.py --session <id> -n 10
```

```
$ python error_tail.py --dir examples/error-tail
session: s9  errors: 2
2026-10-24T10:00:02Z Bash ValueError: x
2026-10-24T10:01:05Z Bash src/a.c:3: error: expected ';'
```

| the tool output looks like | line shown |
|---|---|
| a Python traceback | its last line (`ValueError: x`) |
| compiler or `error:` output | the first line with `error:` |
| a failed Bash call (`is_error`, or `Exit code N` with N ≠ 0) | `Exit code N: ` + the first line with `error`, `ERR!` or `fatal`, else the last non-empty line |

A successful call is never listed, even if its output says `Exit code 0`. The printed line is tool output and can contain anything the tool printed; it stays on your machine.

## Test

```sh
python -m unittest discover -s tests
```

Synthetic transcripts only (hand-written, in `tests/` and `examples/`): streamed duplicates counted once, sub-agent files, two sessions in one project folder, `sessionId` winning over the file name, the concurrency window, the cache share, never printing a share of an allowance; traceback / compiler / Bash failure lines, successful calls left out.
Built by Klavdia (a Haiku colleague); reviewed by Aleksandr, who found that a "session" was the project folder on the real layout (fixed, with tests) and added the sessionId-over-file-name test.

## License

MIT
