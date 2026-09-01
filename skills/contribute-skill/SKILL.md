---
name: contribute-skill
description: "Use when a skill forged locally has proven itself and should be proposed upstream to a shared skill repo, covering the duplicate check against the upstream tree and every pull request in any state, the maintainer-versus-fork decision, and the consent gates that must pass before any network write. Do NOT use for forging, fixing, or retiring a skill (that is skill-compounder), for ordinary code pull requests, or for installing a skill locally."
---

# Contributing a skill upstream

A skill worth forging locally is often worth having in the default pool. This is how it
gets there without wasting a reviewer's time and without pushing anything to the internet
under someone's name that they did not see first.

The procedure has two halves and they are not interchangeable.

- **Sections 1 to 5 are read-only.** They clone, read, compare, stage, and commit, all
  locally. Cloning a public repo over HTTPS creates nothing under anyone's account.
- **Section 6 is nothing but network writes.** Every step there is visible to other
  people and attributable to the user.

Not one line of section 6 may run until gate G6 has returned an explicit yes. If you
reach for a fork, a push, or a pull request while still in sections 1 to 5, you have
already made the mistake, and no later gate can undo it.

`skillcontrib` holds the deterministic parts so this procedure does not have to remember
flags. It performs no network writes at all.

## 0. The bar: both, not either

Propose a skill upstream only when BOTH hold:

- **It came back clean from the `skill-compounder` red-team loop.** Not "the builder
  finished". Clean, from a cold red-teamer that was not a fork of the authoring session.
- **It has been used again since it was forged.** At least one later invocation that did
  the job, in real work, not a rehearsal.

An unproven skill costs a
reviewer more than it saves them: they have to reconstruct evidence the author never
gathered, and a skill nobody has re-run is a guess about the future dressed up as a
capability. Nothing automated can check either condition, so G0 makes the user say it
out loud. If only one holds, keep the skill local and revisit later.

If the skill misfired and you are here to repair it, you want `skill-compounder` section
3, not this.

## 1. Choose the target repo

There is no default worth trusting. Decide where the skill should live, and pass
`--repo <owner>/<repo>` to every `skillcontrib` call. Without it the tool aims at
`ContextLab/claude-skill-compounder`, and a duplicate check pointed at the wrong repo
answers "clean" for free. Name the repo to the user at G1 so a wrong target is caught by
a human and not by a reviewer.

## 2. Preflight the skill (read-only)

```bash
skillcontrib preflight <path-to-skill-dir>
```

`skillcontrib` ships in this repo's `bin/`, and the installer links it into
`~/.local/bin`. If the command is not found, that directory is not on `PATH`: call it by
full path from wherever this repository is cloned, rather than skipping the check.

It checks only what genuinely blocks a contribution: `SKILL.md` exists, the frontmatter
parses with a real YAML parser, `name` matches the directory (Claude Code addresses a skill
by its directory, so a mismatch makes it unreachable), and `description` is present and
non-empty (a skill without one never triggers). It also lists every other
file in the directory. Those travel with the skill: a copy step that takes only
`SKILL.md` silently drops `scripts/`, `references/`, `examples/`, and `LICENSE.txt`.

Length, key portability, and prose style are review topics, not gates. Enforced as gates
they hard-fail 46 of the 156 skills installed on one developer machine, four of them
shipped by Anthropic, while a real parse finds none of the 156 unparseable. Keep them out
of the gate; `CONTRIBUTING.md` is where a human weighs them.

## 3. Identity, permission, and the identity that actually pushes (read-only)

```bash
skillcontrib whoami --repo <owner>/<repo>
```

It prints four things that must all be true before section 6:

- **The acting account** and its **permission level**. `admin`, `write`, or `maintain`
  means `maintainer`: forking is wrong, because it creates a redundant fork of a repo the
  user can already write to. Anything else is `contributor` and takes the fork path.
  Note that the bare `collaborators/<user>` endpoint answers 204 for read-only and triage
  collaborators too, who cannot push at all; `skillcontrib` uses the permission endpoint
  instead. If you check by hand, do the same.
- **The push identity**, read from `git credential fill`. This is the account git will
  actually upload as, and it comes from the credential helper chain (a keychain entry, a
  helper, or `gh auth git-credential`). It can differ from the account `gh` reports,
  in which case the pull request and the commits land under different names.
  `skillcontrib` warns on a mismatch. Resolve it before section 6 rather than hoping.
- **Whether upstream is archived.** Exit 18 means stop: archived repos reject writes.

`gh` acts as `GH_TOKEN` when that variable is set, which is a third possible identity.
`skillcontrib` warns when it is set.

## 4. Duplicate check (read-only)

```bash
skillcontrib dedup <skill-name> --description "<the description, verbatim>" \
  --repo <owner>/<repo>
```

Three probes, cheapest first, because no single key is both precise and complete:

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

The exit code is the whole contract:

|Code|Meaning|What to do|
|-|-|-|
|0|Nothing found|Proceed to section 5|
|3|Mentions, touches, or fuzzy hits|**Ask the user.** Show every row. Never decide alone|
|4|A pull request that proposed this skill is OPEN or MERGED|Stop. It already exists|
|5|A pull request that proposed this skill was CLOSED without merging|Stop and read it|
|9|The skill already exists in the upstream tree|Stop. Improve the existing one|
|18|Upstream is archived|Stop. Find the successor repo|
|19|The tree listing was truncated, so clean cannot be certified|Check by hand. Do not read this as clean|
|8|A lookup failed|A failed lookup is not a clean one. Fix it, or stop|

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

## 5. Stage it locally, then walk the gates. Nothing has been written yet

### 5a. Stage in a read-only clone

Clone upstream over HTTPS and do all the work there. **This is a read.** It creates no
repository, no branch, and no record under anyone's account, and it is the only clone
this procedure needs before consent. Do not reach for a fork to get a working copy.

```bash
git clone https://github.com/<owner>/<repo>.git /tmp/contrib-<name>
cd /tmp/contrib-<name>
git switch -c add-skill-<name>
mkdir -p <skills-dir>/<name>
cp -R <path-to-skill-dir>/. <skills-dir>/<name>/
git add <skills-dir>/<name>
git commit -m "Add <name> skill"
```

Use the layout the tree probe reported for `<skills-dir>`. A clean `skillcontrib dedup`
prints an `upstream keeps skills under:` line naming the directories that actually hold
`SKILL.md` files and how many are in each; a repo that keeps skills at
`plugins/<x>/skills/` does not want a new top-level `skills/`. If that line says no
`SKILL.md` was found anywhere, ask the user rather than inventing a layout. Everything
above is local. Nothing has left the machine.

### 5b. The consent gates

Every gate is required. Do not compress them into one prompt, and do not proceed on
silence or on an ambiguous "sounds good". Walk them in order and show real output.

- **G0. The bar.** State the two conditions from section 0 and have the user confirm
  both, naming the red-team outcome and where the skill has been reused. Nothing checks
  this automatically; if the user cannot name them, stop here.
- **G1. Identity and target.** Print `skillcontrib whoami` verbatim: acting account,
  permission, push identity, any warning. Name the repo chosen in section 1.
- **G2. Full dedup result.** Print every row `skillcontrib dedup` returned, sub-threshold
  ones included, plus the exit code and what it means. The user may overrule either way.
- **G3. State the path out loud.** Say "maintainer path: branching directly on upstream"
  or "fork path: forking to `<owner>/<repo>`", naming the fork's owner. It is the user's
  account unless `--org` puts it under an organization, and whichever it is becomes the
  owner half of `--head <owner>:<branch>` in section 6.
- **G4. Show the change.** From the clone: `git status --short`, `git show --stat HEAD`,
  the branch name, and the commit message. All local.
- **G5. Show the pull request text.** Write the filled-in body to `pr-body.md` in the
  clone and print it, with the exact command that will open the pull request: repo, base,
  head, title, body file. Use upstream's `.github/PULL_REQUEST_TEMPLATE.md` if it has one;
  many repos do not, so fall back to this repo's template as the checklist and paste the
  same headings. Do **not** reach for `--dry-run` here: its own help says
  "May still push git changes", so it is not a read-only preview and does not belong
  before consent.
- **G6. Explicit go-ahead.** Ask as a distinct question and wait for a distinct answer.

Three standing prohibitions:

- **Never auto-retry over a detected rejection.** Exit 5 stops the run. The user decides.
- **Never escalate token scopes.** If a scope is missing, print the exact command for the
  user to run themselves (`gh auth refresh -s repo`) and stop. Do not start an auth flow
  they did not ask for.
- **Never open a pull request whose body and target the user has not read.** It is a
  public, identity-attributed write, and closing one still leaves the record.

## 6. The write sequence. Every step here is a network write

Do not enter this section until G6 returned yes. Work in the clone from 5a; the commit
already exists.

### 6a. Maintainer path (permission `admin`, `write`, or `maintain`)

- **W1.** `git push -u origin add-skill-<name>` (`origin` is upstream on this path).
  Never commit to the default branch directly; the review is the point.
- **W2.** Optional, now that the branch is already uploaded and the caveat costs nothing:
  `gh pr create --repo <owner>/<repo> --dry-run ...` to see the rendered result.
- **W3.** `gh pr create --repo <owner>/<repo> --title "Add <name> skill" --body-file pr-body.md`

### 6b. Fork path (any other permission)

- **W1.** `gh repo fork <owner>/<repo> --remote --remote-name fork`, run inside the clone.
  This creates a repository under the user's account. It is the first write, and it is
  why no earlier step is allowed to need a fork.
- **W2.** If the fork already existed and is behind, `gh repo sync <fork-owner>/<repo>`
  before pushing. **This is a write too**, not a check: it fast-forwards the fork. A
  branch cut from a stale fork produces a diff full of other people's reverts.
  The argument is the **destination**, so it must name the fork. Everywhere else in this
  file `<owner>/<repo>` means upstream, and passing that here would fast-forward
  upstream's default branch instead: a write to a repo the user was never shown at G3 or
  G5, which succeeds for real when upstream is itself a fork.
- **W3.** `git push -u fork add-skill-<name>`. To the fork, never to upstream.
- **W4.** Open the pull request against upstream with an explicit cross-repo head:

```bash
gh pr create --repo <owner>/<repo> --head <fork-owner>:add-skill-<name> \
  --title "Add <name> skill" --body-file pr-body.md
```

Every flag above exists in the installed `gh`. `pr-body.md` is the file written at G5; if
it does not exist, you skipped a gate.

## Failure modes

|Symptom|Detect (read-only)|Response|
|-|-|-|
|`skillcontrib` not found|`command -v skillcontrib`, rc 127|Call it by full path from wherever this repo is cloned. Do not skip the check|
|`gh` not installed|`skillcontrib` exits 6|Stop. Tell the user to install it. Do not hand-roll the REST calls|
|Not authenticated|`skillcontrib` exits 7|Stop. The user runs `gh auth login` themselves|
|GitHub unreachable|`skillcontrib` exits 8, not 7|A network problem. Do not send the user to re-authenticate a session that was never broken|
|Missing token scope|403 on the first write; the scopes line of `gh auth status`|Stop and print `gh auth refresh -s repo`. Never run it for them|
|Push identity mismatch|`skillcontrib whoami` prints both and warns|Resolve before W1. The pull request and the commits would land under different accounts|
|Read-only collaborator|The permission line reads `read` or `triage`|Fork path. The bare 204 check would call it a maintainer and be wrong|
|Fork already exists|`gh repo view <owner>/<repo> --json isFork,parent`|Reuse it and sync at 6b W2. Do not create a second one|
|Fork stale behind upstream|Compare the fork's default-branch SHA to upstream's|`gh repo sync <fork-owner>/<repo>`, inside the write sequence, never before the gates. The argument is the destination: naming upstream writes to upstream|
|Branch name collision|`gh api repos/<owner>/<repo>/branches/<name>` returns 200, not 404|Suffix the branch (`add-skill-<name>-2`). Never force-update someone's branch|
|Upstream archived|`skillcontrib` exits 18|Stop. Find the successor repo|
|Rate limited|`gh api rate_limit --jq .resources.graphql`|Wait for the reset it names. These queries drain graphql, not search|
|Truncated tree listing|`skillcontrib` warns|The tree probe is incomplete. Check by hand before trusting a clean result|

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
- **`gh pr create --dry-run` is not read-only.** Its help says it may still push git
  changes. It belongs after the go-ahead, not before it.
- **A fork is not a way to get a working copy.** `git clone` is. Reaching for a fork to
  stage the change is what quietly turns a read-only preparation step into the first
  irreversible write.

## Known limitations

These are real and unfixed. Read them as part of the procedure, not as small print.

- **The dedup probes cannot prove absence.** The tree probe sees one commit of one
  branch; the pull request probes read a search index that lags by minutes; a very large
  repo truncates the tree listing entirely (exit 19). A clean result means nothing was
  found, not that nothing is there.
- **Fuzzy matching is name-shaped, not meaning-shaped.** The same idea proposed under a
  genuinely different name and vocabulary will not be found by any probe here. Only a
  human who knows the domain catches that, which is why G2 shows the user every row.
- **The gates are instructions, not enforcement.** Nothing in the tooling can stop a
  session from skipping to section 6; `skillcontrib` simply has no write in it. The
  guarantee is that the tool cannot write, not that the procedure cannot be skipped.
- **The tests check this document and the tool, not a real contribution.** One test
  executes the read-only staging block against a local git repo. No test opens a pull
  request, so the write sequence in section 6 is verified by flag inspection and by
  reading `gh`'s help, not by having been run end to end.

## Trigger precision

<!-- routing-pin
description-sha256: f2f816f2d07f872183036d47e56a63aa007c8665174ab3fc40f4412bcd55428c
prompts-sha256: 7140c84e539131ff411a8ddb9fcc2fdd29cea180fe3e660285620f65df5c3efd
measured: 2026-08-31
cli: 2.1.252 (Claude Code)
model: sonnet
runs: 3
result: verified 9/9 must-fire draws, 9/9 must-not-fire draws (3/3 each prompt over 3 runs) Re-measured after two em-dashes were removed from the prompt list on 2026-08-31, which moved prompts-sha256.
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
