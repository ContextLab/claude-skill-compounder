# 2026-11-21: the /insights journey, run under the CLI's own login

What was run: `python3 tests/journeys/journey_insights.py --config ambient`, twice (the
second after a fix to the script), plus `--dry` under both `--config ambient` and
`--config fresh`. Model: haiku for every session. Counts only below: no session text, no
ids, no project names.

## Mode

`--config ambient`: every `claude` the journey started, the worker, and the child
`claude -p /insights` used the user's own configuration and login (no `CLAUDE_CONFIG_DIR`).
`/insights` read the user's real sessions and wrote under the real `~/.claude/usage-data`,
as it does when typed. `COMPOUND_CLAUDE_DIR` was left unset so the CLI read that same
directory; `COMPOUND_HOME` was a temporary directory in every process. The journey's
sessions run with `--setting-sources project` and `--plugin-dir <working copy>` and
`CLAUDE_CODE_PLUGIN_DIRS=""`, so the user's settings (whose `env` names the main checkout's
older mod) did not apply to them; the child reads the user's settings and so loads what they
name, with `COMPOUND_OFF=1` and the temporary `COMPOUND_HOME` from the worker's environment.
The journey was started with the variables of the calling Claude Code session removed from
its environment.

## First run: 24 of 26, a script fault

Every check passed except the two of e. The `remind` event of the later session named 3
findings, but the script looked for the `RECORDED-INSIGHT` block in the `-p` stream, and
what a hook adds to a typed prompt is not in that stream. The block was in the session's
transcript (two occurrences, counted without reading the text). The script now reads the
transcript. Not a product fault.

## Second run: 26 of 26

| Check | Outcome |
|-|-|
| load | the first session's init listed exactly one `compound` plugin, the working copy; its events were in the temporary log; no line the real log gained named it |
| seed | three sessions, the two build sessions met the failing build and worked around it |
| f | no seed session (DAYS=0, MIN_SESSIONS=1) started a run; `insights --start` answered `disabled` |
| a | the starting session's first prompt started the run; the worker held the lock after that session exited; `running -> ok`; lock free, no worker left |
| b | a second session's first prompt during the run did not start another (`started` unchanged); exactly one new `report-*.html` |
| c | `report.html` under the real usage-data newer than the start; nothing under the temporary root's configuration directories |
| d | no event of the child in the temporary log; one child transcript, in Claude Code's project folder for the temporary `COMPOUND_HOME`, left in place |
| e | the harvest recorded 16 facet findings (none about the scratch project) and 5 report findings from 59 facets read (0 skipped, 0 dropped, 0 capped); 5 findings were listed for the scratch project (the report's); a later session's first prompt held 3 `RECORDED-INSIGHT` blocks with `in-` ids, read from its transcript, and its `remind` named the same ids |
| g | 50 s from the starting prompt to a free lock (65 s in the first run); no output reports what `/insights` cost (the child's output is discarded); the journey's own sessions reported 0.04 USD |
| real | `~/.claude/compound/insights.json` absent before and after; no line the real event log gained named any of the 7 sessions of the journey (the child included); its size was the same before and after the second run |

Facet kinds named, counts: buggy_code 6, wrong_approach 4, user_rejected_action 3, and one
each of external_environment, misunderstood_request, tool_failure, tool_guard_blocks,
tool_error, tool_blocked.

## Proven, and not

Proven: the live path from a real session's first typed prompt through the detached worker,
the real `claude -p /insights` under the CLI's login, the harvest of its real output, and a
later first prompt that quotes a finding, with the real store untouched and one run only.

Not proven: a facet finding about the scratch project's own sessions reaching its sessions
(`/insights` named none for sessions this short; the leg was proven with report findings);
the cost of `/insights` itself; `--config fresh` beyond its dry check (it needs a credential
in the environment). Two runs of `/insights` were made, each incremental over the user's
sessions. The temporary roots were removed; the journey's session transcripts stay in
Claude Code's project folders, as with the other ambient journeys.
