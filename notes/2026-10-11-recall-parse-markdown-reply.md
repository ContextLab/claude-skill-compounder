# 2026-10-11: recall replies that were not bare JSON

Branch `fix/recall-parse-markdown-reply`, from `main` at 9567d24. Not pushed, not merged.

## What happened

The event log (`~/.claude/compound/events.jsonl`, 4 to 11 October, 1616 events) holds 232
recall questions put to the model: 125 `named`, 105 `none`, 2 `unreadable`. The two:

- 8 October: a JSON object naming a lesson inside a code fence, followed by an
  explanation that itself held a `${...}` shell expansion.
- 11 October: no JSON; a lesson's name in bold as the first word, followed by an
  explanation.

Reuse (455 calls) and fix (256 calls) had no unreadable reply.

## Cause

- `firstObject` (`hooks/judge.ts`) parsed the span from the first `{` to the LAST `}`. The
  first reply's explanation holds a `${...}` expansion, so the span ran past the answer and was not
  JSON.
- `parseRecall` took nothing but a JSON object. The second reply has none.

## Change

- `recallPrompt`: one more line, "No markdown, no code fence, no explanation. The first
  character of your reply is { and the last is }."
- `firstObject`: when the first-to-last span is no object, each `{...}` that closes is
  tried; one distinct object is the answer, two that differ are none. This serves the
  reuse and fix replies too.
- `parseRecall`: with no JSON, the reply is read only when its first word is a lesson it
  was shown (inside `*`, `_`, backticks or quotes) and no other shown lesson is mentioned.
  A name further in, an unknown name, two names, or a broken `{"name"` stay unreadable.
- `docs/design.md`: how a recall reply is read.

## Checked

`claude plugin test .` 287 pass (282 before, 5 added; 4 of the 5 failed before the change),
`npx tsc --noEmit -p .` clean, `claude plugin validate --strict .` passed, `./run_tests.sh`
23 files OK, `python3 tests/journeys/journey_recall.py` 23 of 23 (real sessions).

## Left

- The reuse and fix prompts were not given the new line: neither has had an unreadable reply.
- `claude plugin validate --strict .` passes but advises a marketplace install line in the
  README; not touched.
