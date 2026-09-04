---
name: contribute-skill
description: "Use when a skill forged locally has proven itself and should be proposed upstream to a shared skill repo, covering the duplicate check against the upstream tree and every pull request in any state, the maintainer-versus-fork decision, and the consent gates that must pass before any network write. Do NOT use for forging, fixing, or retiring a skill (that is skill-compounder), for ordinary code pull requests, or for installing a skill locally."
---

# Contributing a skill upstream

A skill worth forging locally is often worth having in the default pool. This is how it
gets there without wasting a reviewer's time and without pushing anything to the internet
under someone's name that they did not see first.

The whole procedure is two commands, and the second one is the consent:

```bash
skillcontrib recon <skill-name> --upstream <owner>/<repo>
skillcontrib propose <skill-name> --upstream <owner>/<repo>
```

`recon` reads. It clones nothing, forks nothing, and pushes nothing; it is
`propose --dry-run` under a second name, so a reader told to run the dry run first has a
command that cannot be turned into a write by dropping a flag. `propose` without
`--dry-run` forks if it has to, pushes a branch, and opens a public pull request under the
acting account. Running it is the yes. There is no gate after it.

That is a change from how this file used to read, and the reason is a count. The earlier
version put seven consent gates in front of the write sequence, each one a thing a session
had to print and a human had to answer. The record for that version, audited on
2026-09-03 and written up in `notes/2026-09-03-mission-and-lessons-design.md`, is 47 runs
and 0 pull requests ever. Every gate held; nobody reached the far side. So
the seven collapse into one act, and everything the gates used to display is printed by
the command itself, before the thing it describes happens. Read the dry run. Then run it.

## 0. The bar: both, not either

Propose a skill upstream only when BOTH hold:

- **It came back clean from the `skill-compounder` red-team loop.** Not "the builder
  finished". Clean, from a cold red-teamer that was not a fork of the authoring session.
- **It has been used again since it was forged.** At least one later invocation that did
  the job, in real work, not a rehearsal.

An unproven skill costs a
reviewer more than it saves them: they have to reconstruct evidence the author never
gathered, and a skill nobody has re-run is a guess about the future dressed up as a
capability. Nothing automated can check either condition. The dry run prints the ledger's
own answer to the second one, and it is a floor rather than a total, so ask the user to
name both before you type either command. If only one holds, keep the skill local and
revisit later.

If the skill misfired and you are here to repair it, you want `skill-compounder` section
3, not this.

## 1. Choose the target repo

There is no default worth trusting. Decide where the skill should live, and pass
`--upstream <owner>/<repo>` to both commands. Without it they aim at
`ContextLab/claude-skill-compounder`, and a duplicate check pointed at the wrong repo
answers "clean" for free. Name the repo to the user before the dry run, so a wrong target
is caught by a human and not by a reviewer.

## 2. Run the dry run

```bash
skillcontrib recon <skill-name> --upstream <owner>/<repo>
```

`skillcontrib` ships in this repo's `bin/`, and the installer links it into
`~/.local/bin`. If the command is not found, that directory is not on `PATH`: call it by
full path from wherever this repository is cloned, rather than skipping the check.

Steps 1 to 3 run for real, because they only read. Steps 4 to 6 are printed as a plan.

|Step|What runs in a dry run|
|-|-|
|1|Finds the skill at `~/.claude/skills/<name>`, resolved through its symlink, or at `./.claude/skills/<name>`. Parses the frontmatter with a real YAML parser, checks `name` against the directory and that `description` is non-empty, lists every other file in the directory, and reads the routing pin out of the `## Trigger precision` section|
|2|The duplicate check, in three probes, using the skill's own description|
|3|The acting account, its permission level, the push identity, and therefore maintainer or fork. The fork itself is printed as a plan, not created|
|4|Prints the clone source, the branch `skill/<name>`, the destination `<skills-dir>/<name>/`, and the commit message|
|5|Prints the pull request command and the whole body it would send|
|6|Prints the ledger row it would append|

Step 1 refuses a skill whose routing pin says `measured: never`. That pin is the only
machine-readable evidence that the description was ever run against a router, and without
it "this fires on the right prompts" is a claim a reviewer can neither check nor re-run.
`--allow-unmeasured` proceeds anyway, and then the pull request body says so.

Step 2 is three probes, cheapest first, because no single key is both precise and
complete:

|Probe|Question|Catches|Misses|
|-|-|-|-|
|tree|Does any directory in the upstream default branch hold `<name>/SKILL.md`?|A skill that already ships, at any depth, under any casing or separator|A shipped skill under a genuinely different name|
|files|Does any pull request, in any state, ADD `<name>/SKILL.md` outright?|Literal proposals: open, merged, or closed|The same idea proposed under a different name|
|fuzzy|Do the description's tokens overlap pull request titles?|Renamed duplicates|Nothing, but it produces real false positives|

The tree probe is one recursive listing of the whole default branch, and it compares on
a normalised key (lowercased, non-alphanumerics dropped). Both details are load-bearing.
A direct path lookup at `skills/<name>/` is case-exact and separator-exact, so
`Internal-Comms` and `internal_comms` walk straight past a repo that ships
`internal-comms`; and it only ever sees one layout, so it misses
`plugins/<x>/skills/<x>/SKILL.md`, which is how a real Anthropic repo is arranged. If the
listing comes back truncated, `skillcontrib` says so, and the probe is then incomplete.

Step 3 reads the permission endpoint rather than the bare `collaborators/<user>` one,
which answers 204 for read-only and triage collaborators who cannot push at all. `admin`,
`write` or `maintain` is `maintainer`, and forking is then wrong: it makes a redundant
fork of a repo the user can already write to. Anything else is `contributor` and takes the
fork path, where the branch goes to the fork and the pull request is opened cross-repo
with `--head <fork-owner>:skill/<name>`.

It also prints the **push identity**, read from `git credential fill`. That is the account
git will actually upload as, and it comes from the credential helper chain, so it can
differ from the account `gh` reports; when it does, the pull request and the commits land
under different names. `gh` acts as `GH_TOKEN` when that variable is set, which is a third
possible identity, and the dry run warns when it is. Resolve a mismatch before step 4,
rather than hoping.

## 3. Read the dry run

The dry run is the review that the seven gates used to be, and it is worth reading rather
than skimming for the exit code. Five things, and then the code:

1. **The skill directory it found.** Under a symlinked install the path it prints is the
   checkout, not the link. If it is not the skill you meant, nothing later will notice.
2. **Every duplicate row**, sub-threshold fuzzy ones included. The user may overrule
   either way, and the rows below the threshold are printed precisely because a person
   has to read them.
3. **Maintainer or fork**, and which account owns the fork. That account becomes the owner
   half of `--head <owner>:<branch>`.
4. **The commit**: the branch name, the destination path, and every file that travels with
   `SKILL.md`. A `scripts/` or `references/` directory left behind makes the skill arrive
   broken.
5. **The pull request body in full**, which the dry run prints between two markers. It
   carries the description, the routing pin's own result line, and the ledger's counts for
   this skill. Those counts come from one machine and say the skill was used, not that
   anyone else used it.

The exit code is the whole contract, and it is the same one on both commands:

|Code|Meaning|What to do|
|-|-|-|
|0|Nothing found|Proceed|
|3|Mentions, touches, or fuzzy hits|**Ask the user.** Show every row. Never decide alone|
|4|A pull request that proposed this skill is OPEN or MERGED|Stop. It already exists|
|5|A pull request that proposed this skill was CLOSED without merging|Stop and read it|
|9|The skill already exists in the upstream tree, or in the clone|Stop. Improve the existing one|
|18|Upstream is archived|Stop. Find the successor repo|
|19|The tree listing was truncated, so clean cannot be certified|Check by hand. Do not read this as clean|
|8|A lookup failed|A failed lookup is not a clean one. Fix it, or stop|
|10, 11, 12, 17|The skill is missing, or its frontmatter does not parse, or `name` disagrees with the directory|Fix the skill. A name that disagrees with its directory makes it unreachable|
|20, 21, 22|No `## Trigger precision` section, no routing pin, or an unmeasured one|Measure it, or pass `--allow-unmeasured` and say so in review|
|23, 24, 25|The fork, a git step, or `gh pr create` failed|These only happen on a real run. Read the message: it says what was already written|

Exit 5 is deliberately hard to trigger: it requires a pull request to have **added** the
skill file wholesale, not merely mentioned or edited it, so a typo fix inside an existing
skill is reported as a `touch`. When it does fire, do not call it a rejection. A closed
unmerged proposal is just as often a revision the author superseded with a later pull
request, and the difference is not machine-readable. Show the user the number, title, and
URL, have them read why it closed, and look for a successor by the same author. Only then,
and only if they say to proceed, re-run with `--override-rejected`, which downgrades the
block to a question rather than silencing it. Never pass that flag on your own judgment.

Three limits of the lookup, to state plainly rather than paper over:

- The pull request probes read GitHub's **search index**, which lags creation by seconds
  to minutes. A duplicate opened moments ago can be invisible.
- The fuzzy probe scores token overlap against titles and flags unrelated work that
  shares vocabulary. Rows below the threshold are printed but not counted, so read the
  list rather than only the exit code.
- These queries drain the **graphql** budget, not the search one. Check
  `gh api rate_limit --jq .resources.graphql` if calls start failing.

## 4. Run it for real

```bash
skillcontrib propose <skill-name> --upstream <owner>/<repo>
```

Steps 1 to 3 run again, so a duplicate opened between the two commands still stops it. Then:

- **Step 4** shallow-clones the target over HTTPS, cuts `skill/<name>`, copies the whole
  skill directory to `<skills-dir>/<name>/`, commits with the routing pin's `measured:`
  line in the message, and pushes. The clone is a read; it creates nothing under anyone's
  account, and it is the only clone this procedure needs. Do not reach for a fork to get a
  working copy. If `<skills-dir>/<name>/` already exists in the clone, the run stops with
  exit 9 rather than overwriting it: that is a duplicate the tree probe did not see.
- **Step 5** opens the pull request against the upstream default branch with
  `gh pr create`, cross-repo on the fork path, and prints the URL.
- **Step 6** appends one `contrib` row to the ledger naming the skill, the pull request,
  the upstream, and whether a fork was used.

**Every network write is announced first, on its own line beginning `WRITE:`.** There are
at most three: the fork, the push, and `gh pr create`. Nothing else in `bin/skillcontrib`
writes to the network at all, so a transcript can be swept for that prefix and the answer
is complete. The run stops at the first failure, and each message says what had already
been written by then. Read that sentence before re-running anything: after a failed
`gh pr create` the branch is already pushed, and a second `propose` will try to push it
again.

Three standing prohibitions:

- **Never auto-retry over a detected rejection.** Exit 5 stops the run. The user decides,
  and `--override-rejected` is theirs to grant, never yours to assume.
- **Never escalate token scopes.** If a scope is missing, print the exact command for the
  user to run themselves (`gh auth refresh -s repo`) and stop. Do not start an auth flow
  they did not ask for.
- **Never run the second command against a dry run the user has not seen.** The body and
  the target are in that output. Skipping it does not skip the write; it skips the review.

## Failure modes

|Symptom|Detect|Response|
|-|-|-|
|`skillcontrib` not found|`command -v skillcontrib`, rc 127|Call it by full path from wherever this repo is cloned. Do not skip the check|
|`gh` not installed|Exit 6|Stop. Tell the user to install it. Do not hand-roll the REST calls|
|Not authenticated|Exit 7|Stop. The user runs `gh auth login` themselves|
|GitHub unreachable|Exit 8, not 7|A network problem. Do not send the user to re-authenticate a session that was never broken|
|Missing token scope|403 on the first write; the scopes line of `gh auth status`|Stop and print `gh auth refresh -s repo`. Never run it for them|
|Push identity mismatch|The dry run prints both and warns|Resolve before the real run. The pull request and the commits would land under different accounts|
|Read-only collaborator|The permission line reads `read` or `triage`|Fork path. The bare 204 check would call it a maintainer and be wrong|
|Fork already exists|The dry run says it is reused|Reused, not created again. A second fork is never made|
|Skill not found locally|Exit 10|It is not installed under either skills directory. Install it, or run from the project that holds it|
|Routing pin unmeasured|Exit 22|Measure it. `--allow-unmeasured` proceeds and the body then says the trigger is unmeasured|
|Branch name collision on the fork|Exit 24: `git push` is refused rather than forced|Nothing of someone else's was overwritten. Delete or rename the old branch yourself, then re-run|
|`gh pr create` failed|Exit 25|The branch IS pushed. Open the pull request by hand; do not re-run `propose`|
|Upstream archived|Exit 18|Stop. Find the successor repo|
|Rate limited|`gh api rate_limit --jq .resources.graphql`|Wait for the reset it names. These queries drain graphql, not search|
|Truncated tree listing|Exit 19|The tree probe is incomplete. Check by hand before trusting a clean result|

## Traps that produce a confidently wrong answer

- **A pull request search alone misses skills that already ship.** Check the tree. The
  pull request that added a skill may predate the search window or never name it in the
  title.
- **An exact path lookup is not a duplicate check.** It is defeated by a capital letter,
  an underscore, or a nested layout. Normalise both sides and search the whole tree.
- **`--limit 100` is load-bearing.** The default page size is 30, so a sweep without it
  silently misses older pull requests and reports "no duplicate".
- **`gh api search/issues -f q=...` answers 404.** Passing `-f` flips `gh api` to POST,
  and `POST /search/issues` does not exist. If you need the search API for a qualifier
  `gh pr list --search` does not expose, it must be `-X GET`.
- **A merged pull request is a closed one.** Read the JSON `state` field, which separates
  `MERGED` from `CLOSED`, not the open/closed distinction.
- **`gh pr create --dry-run` is not read-only.** Its help says
  "May still push git changes". `skillcontrib recon` is the preview; that flag is not.
- **A fork is not a way to get a working copy.** `git clone` is, which is what step 4
  does. Reaching for a fork to stage a change is what quietly turns a read-only
  preparation step into the first irreversible write.
- **A dry run that exits 0 has not checked the bar.** Section 0 is the one condition no
  probe reaches.

## Known limitations

These are real and unfixed. Read them as part of the procedure, not as small print.

- **The dedup probes cannot prove absence.** The tree probe sees one commit of one
  branch; the pull request probes read a search index that lags by minutes; a very large
  repo truncates the tree listing entirely (exit 19). A clean result means nothing was
  found, not that nothing is there.
- **Fuzzy matching is name-shaped, not meaning-shaped.** The same idea proposed under a
  genuinely different name and vocabulary will not be found by any probe here. Only a
  human who knows the domain catches that, which is why every row is printed.
- **One command is one consent, and it is coarse.** The old seven gates could be answered
  one at a time; this cannot. What replaces them is that the dry run is complete, so the
  reviewer sees the body, the target and the writes before any of them happen. A session
  that runs `propose` without reading `recon` has skipped the review, and nothing in the
  tooling can tell.
- **The ledger counts are one machine's.** "Used again since it was forged" is answered
  from a local ledger that only knows what this machine recorded, and a session audit's
  totals there are a floor rather than a count.
- **The tests use a local git origin and a stand-in `gh`.** The clone, branch, commit and
  push are real, against real repositories on disk, and are read back out of a bare repo.
  No test opens a pull request on GitHub, so `gh pr create`'s own flags are verified by
  reading `gh`'s help, not by having been run against the service.

## Trigger precision

<!-- routing-pin
description-sha256: f2f816f2d07f872183036d47e56a63aa007c8665174ab3fc40f4412bcd55428c
prompts-sha256: 7140c84e539131ff411a8ddb9fcc2fdd29cea180fe3e660285620f65df5c3efd
measured: 2026-09-01
cli: 2.1.252 (Claude Code)
model: sonnet
runs: 3
result: verified 9/9 must-fire draws, 9/9 must-not-fire draws (3/3 each prompt over 3 runs)
-->

Prompts that MUST fire this skill:

1. "That deploy-check skill has earned its keep: can we get it into the shared repo?"
2. "I want to send the stale-artifact-check skill upstream. Walk me through it."
3. "We've been using this skill locally for weeks. How do I propose it to the main skills repo so other people get it?"

Prompts that must NOT fire this skill:

1. "This skill fires on the wrong prompts. Fix it." (`skill-compounder` owns fixing,
   forging and retiring a skill; this one owns proposing a proven skill upstream.)
2. "Open a pull request for the bug fix on this branch." (An ordinary code pull request.
   Nothing about it is a skill, and the duplicate check and consent gates here would be
   noise.)
3. "Install the session-handoff skill on this machine." (Local installation, which
   `skillforge done` does. Nothing leaves the machine, so none of the network-write
   gates below apply.)
