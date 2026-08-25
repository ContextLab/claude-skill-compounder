---
name: contribute-skill
description: Use when a skill forged locally has proven itself and should be proposed upstream to a shared skill repo, covering the duplicate check against every pull request in any state, the maintainer-versus-fork decision, and the consent gates before any network write. Do NOT use for forging, fixing, or retiring a skill (that is skill-compounder), for ordinary code pull requests, or for installing a skill locally.
---

# Contributing a skill upstream

A skill worth forging locally is often worth having in the default pool. This is how it
gets there without wasting a reviewer's time and without pushing anything to the internet
under someone's name that they did not see first.

Everything deterministic lives in `skillcontrib`, so this procedure does not have to
remember flags. That script performs no network writes at all. Every write happens here,
in steps 4 and 5, after the consent checklist.

## 0. The bar: both, not either

Propose a skill upstream only when BOTH hold:

- **It came back clean from the `skill-compounder` red-team loop.** Not "the builder
  finished". Clean, from a cold red-teamer that was not a fork of the authoring session.
- **It has been used again since it was forged.** At least one later invocation that did
  the job, in real work, not a rehearsal.

This was an open question and it is now settled at "both". An unproven skill costs a
reviewer more than it saves them: they have to reconstruct the evidence the author never
gathered, and a skill that no one has re-run is a guess about the future dressed up as a
capability. If only one condition holds, keep the skill local and revisit after it earns
the second one.

If the skill misfired and you are here to repair it, you want `skill-compounder` section
3, not this.

## 1. Preflight the skill

```bash
skillcontrib preflight ~/.claude/skills/<name>
```

This checks what a reviewer would otherwise check by hand: SKILL.md exists, the
frontmatter parses, it uses only the six portable keys (`name`, `description`, `license`,
`compatibility`, `metadata`, `allowed-tools`), `description` is at most 500 characters,
the frontmatter is at most 1024 characters, and the body is at most 500 lines. Each
failure exits with its own code and a specific message. Fix the skill; do not argue with
the limits, they are what keeps a skill loadable outside Claude Code.

## 2. Identity and path

```bash
skillcontrib whoami --repo <owner>/<repo>
```

It prints the acting GitHub account, the target repo, whether the upstream is archived,
and one of two roles:

- **`maintainer`**: the account already has push access. A collaborator check answers
  HTTP 204 for these accounts. Forking is wrong here. It creates a redundant fork of a
  repo the user can already write to, and it confuses the review.
- **`contributor`**: no push access. Fork path.

These are two different procedures below, not one procedure with a footnote. Read the
role before reading step 5.

## 3. Duplicate check

```bash
skillcontrib dedup <skill-name> --description "<the description: line, verbatim>" \
  --repo <owner>/<repo>
```

Two layers, because no single key is both precise and complete:

|Layer|Catches|Misses|
|-|-|-|
|Exact: skill directory name and `name:` frontmatter|Literal resubmission, renames of the identical skill|The same idea proposed under a different name|
|Fuzzy: `description:` tokens against pull request titles|Renamed duplicates|Nothing, but it produces real false positives|

The exit code is the whole contract:

|Code|Meaning|What to do|
|-|-|-|
|0|No match in any state|Proceed to step 4|
|3|Fuzzy matches present, including sub-threshold ones|**Ask the user.** Show every row. Never decide this alone|
|4|Exact match on an OPEN or MERGED pull request|Stop. The contribution already exists|
|5|Match on a CLOSED-unmerged pull request|Stop. A maintainer already declined this|

Exit 5 is the one that matters most. A declined proposal is a signal, not noise to route
around. Show the user that pull request's number, title, and URL, and let them read the
review before anything else happens. Only if they then say to proceed do you re-run with
`--override-rejected`, which downgrades the block to a question (exit 3 or 4) rather than
silencing it. Never pass that flag on your own judgment.

Two limits of the lookup, which you must state to the user rather than paper over:

- It reads GitHub's **search index**, and the index lags pull request creation by seconds
  to minutes. A duplicate opened moments ago can be invisible. Absence of evidence here is
  not evidence of absence.
- The fuzzy layer scores token overlap between the description and pull request titles. It
  will flag unrelated work that happens to share vocabulary. That is the intended failure
  direction: it asks, it does not decide.

## 4. Consent checklist, before ANY network write

Every item is required. Do not summarize them into one prompt, and do not proceed on
silence or on an ambiguous "sounds good". Walk them in order and show the actual output.

1. **Identity and target.** Print the `skillcontrib whoami` output verbatim. The user
   sees whose account the contribution goes out under and against which repo.
2. **Full dedup result.** Print every row `skillcontrib dedup` returned, including the
   sub-threshold fuzzy ones, plus the exit code and what it means. The user can overrule
   the tool in either direction: skip a hit that is obviously unrelated, or hold back on
   one the tool ranked low.
3. **State the path out loud.** Say "maintainer path: branching directly on upstream" or
   "fork path: forking to `<user>/<repo>`". Name the fork's owner. An `--org` value would
   change who owns it, so if one is in play, say so.
4. **Show the change.** `git status --short` and `git diff --stat` for exactly what will
   be committed, plus the branch name and the commit message, before anything leaves the
   machine.
5. **Dry run the pull request.** Run the creation command with `--dry-run`. It prints the
   title, body, base, and head without opening anything. Show that output.
6. **Explicit go-ahead.** Ask for it as a distinct question and wait. Then, and only then,
   drop `--dry-run`.

Three standing prohibitions:

- **Never auto-retry over a detected rejection.** Exit 5 stops the run. The user decides.
- **Never escalate token scopes on the user's behalf.** If a scope is missing, print the
  exact command they should run themselves (`gh auth refresh -s repo`) and stop. Do not
  start an auth flow they did not ask for.
- **Never open a pull request the user has not seen the dry run of.** A pull request is a
  public, identity-attributed write. Closing one still leaves the record.

## 5a. Maintainer path (role: `maintainer`)

No fork. Work in a clone of upstream.

```bash
git clone https://github.com/<owner>/<repo>.git && cd <repo>
git switch -c add-skill-<name>
mkdir -p skills/<name> && cp ~/.claude/skills/<name>/SKILL.md skills/<name>/
git add skills/<name>
git commit -m "Add <name> skill"
```

Then gate 4, then push the branch to `origin` (which is upstream here) and open the pull
request from that branch. Do not target the default branch directly with a commit; the
review is the point.

## 5b. Fork path (role: `contributor`)

```bash
gh repo fork <owner>/<repo> --clone --remote     # origin = your fork, upstream = theirs
cd <repo>
git switch -c add-skill-<name>
mkdir -p skills/<name> && cp ~/.claude/skills/<name>/SKILL.md skills/<name>/
git add skills/<name>
git commit -m "Add <name> skill"
```

Then gate 4, then push the branch to `origin` (the fork, never upstream), and open the
pull request against upstream with an explicit cross-repo head:

```bash
gh pr create --repo <owner>/<repo> --head <your-user>:add-skill-<name> \
  --title "Add <name> skill" --body "$(cat pr-body.md)"
```

Every flag above was confirmed against the installed `gh`. Fill the body from
`.github/PULL_REQUEST_TEMPLATE.md`: red-team rounds and their findings, the trigger
prompts, the fixture, and the local-reuse evidence. If the evidence is not in the body,
the reviewer has to go find it, and the contribution stalls.

## Failure modes

|Symptom|Detect|Response|
|-|-|-|
|`gh` not installed|`command -v gh`; `skillcontrib` exits 6|Stop. Tell the user to install it. Do not attempt the REST API by hand|
|Not authenticated|`gh auth status`; `skillcontrib` exits 7|Stop. The user runs `gh auth login` themselves|
|Missing token scope|403 on the first write; `gh auth status` scopes line|Stop and print `gh auth refresh -s repo`. Never run it for them|
|Fork already exists|`gh repo view <user>/<repo> --json isFork,parent`|Reuse it. Do not create a second one under a different name|
|Fork stale behind upstream|Compare the fork's default-branch SHA to upstream's|`gh repo sync <user>/<repo>`, then branch. A branch off a stale fork produces a diff full of other people's reverts|
|Branch name collision|`gh api repos/<user>/<repo>/branches/<name>` returns 200 instead of 404|Suffix the branch (`add-skill-<name>-2`). Never force-update someone's branch|
|Upstream archived|`gh repo view <repo> --json isArchived`; `skillcontrib whoami` prints it|Stop. Archived repos reject writes. Find the successor repo|
|Rate limited|`gh api rate_limit`; search is 30/min against core's 5000/hr|Wait for the reset the response names. Do not loop the dedup search per file|
|Dedup lookup failed|`skillcontrib` exits 8|Do not treat a failed lookup as a clean one. Fix the lookup, or stop|

## Traps that produce a confidently wrong answer

- **`--limit 100` is load-bearing.** The default page size is 30. A sweep without it
  silently misses older pull requests and reports "no duplicate".
- **`gh api search/issues -f q=...` answers 404.** Passing `-f` flips `gh api` to POST,
  and `POST /search/issues` does not exist. If you need the search API for a qualifier
  `gh pr list --search` does not expose, it must be `-X GET`.
- **`repos/<r>/pulls?state=all` has no text search.** Filtering it means paginating
  everything and matching client-side. It is a fallback, not a default.
- **A merged pull request is a closed one.** The JSON `state` field is what separates
  `MERGED` from `CLOSED`, so read `state`, not the open/closed distinction.
