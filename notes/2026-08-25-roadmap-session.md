# 2026-08-25 — animation, research, roadmap

Two sessions worked this repo concurrently. This one produced the README animation, the
five research investigations, and issues #2–#6. The other forged
`parallel-agents-one-codebase` and rewrote the demo transcript to replay that real forge.

## Done

- `docs/media/forge.gif` + `dev/{forge_demo.sh,forge.tape,generate_media.sh}` — a simulated
  Claude Code session whose bottom block is the real status line driven by the real state file.
- Animation defects fixed: box width now from `tput cols` (a hardcoded 118 against a 117-column
  terminal wrapped the box, which produced both the "garbage in the corner" and the bar appearing
  only at the end); DEC scroll region instead of cursor arithmetic; dense braille spinner.
- `bin/skillforge start` writes its state file atomically. A plain redirect truncated first, and a
  status-line render inside that window blanked the segment for a frame.
- README, SKILL.md, CLAUDE.md, DESIGN.md audited for AI tells against measured criteria.
- Tuning table corrected: only the three `CI_*` variables are read by the hook.

## Corrections to earlier notes

`notes/2026-08-24-origin.md` lists as an open question that "the forging protocol is written but
has not yet been *run* end to end on a real candidate skill." **That is no longer true.** The
concurrent session ran it on `parallel-agents-one-codebase`, and the demo replays those real
red-team findings.

## Research, all in notes/research/

|File|The finding that mattered|
|-|-|
|`seed-skill-candidates.md`|4 of 12 candidates survive the evidence bar. The loudest complaint in the corpus is a *reject*: `superpowers:verification-before-completion` already owns that trigger.|
|`skill-ecosystem-survey.md`|105 unique skills already installed. Measured house style: body median 200 lines, cap 500; description ≤500 chars as a pure "Use when" clause.|
|`insight-capture.md`|Universal/local classification by identifier matching scores **7/14, chance**. Subagents emit zero `★ Insight` blocks across 1,428 transcripts.|
|`contribute-back-mechanics.md`|`gh api search/issues -f q=` 404s because `-f` flips it to POST. Default page size 30, so a dedup sweep without `--limit` silently concludes "no duplicate".|

## Decisions taken

1. One-liner install is a hard constraint. This favours a **skills-directory plugin**
   (auto-loads from `~/.claude/skills/`, no marketplace, no install step), with the installer
   reduced to setting `statusLine`, which plugins cannot carry. Five verification items in #5.
2. Seed pool is **four** skills, not 5–10.
3. Stop writing to the author's voice. His style guide forbids deriving a README voice from it.
   The standing instruction is an AI-tell audit instead.

## Next

~~#5 first (small, unblocks #3). #6 in parallel starting now, because it is the only item needing
elapsed time. Then #3, then #4, then #2.~~

**Done 2026-08-25**, all five, on branch `roadmap-issues-2-6`. See
`2026-08-25-implementation-session.md` for what landed, what broke along the way, and the
three items that still need calendar time rather than code.

## Watch out for

Two sessions on one checkout. Files were rewritten underneath this session three times
(`statusline/skillforge-status.sh`, `dev/forge_demo.sh`, `README.md`). Check `git status` and
re-read before editing. This is exactly what `parallel-agents-one-codebase` exists to prevent.
