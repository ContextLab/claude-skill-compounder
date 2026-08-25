---
name: contribute-skill
description: "Use when a skill forged locally has proven itself and should be proposed upstream to a shared skill repo, covering the duplicate check against the upstream tree and every pull request in any state, the maintainer-versus-fork decision, and the consent gates that must pass before any network write. Do NOT use for forging, fixing, or retiring a skill (that is skill-compounder), for ordinary code pull requests, or for installing a skill locally."
---

# Contributing a skill upstream

A skill worth forging locally is often worth having in the default pool. This is how it
gets there without wasting a reviewer's time and without pushing anything to the internet
under someone's name that they did not see first.

The procedure has two halves and they are not interchangeable. **Sections 1 to 4 are
read-only.** Nothing in them touches the network in a way anyone else can see. **Section 5
is nothing but network writes.** Not one line of section 5 may run until gate G6 in
section 4 has returned an explicit yes. If you find yourself in section 5 without having
walked G1 to G6, you have already made the mistake.

`skillcontrib` is where the deterministic parts live, so this procedure does not have to
remember flags. It performs no network writes at all.

## 0. The bar: both, not either

Propose a skill upstream only when BOTH hold:

- **It came back clean from the `skill-compounder` red-team loop.** Not "the builder
  finished". Clean, from a cold red-teamer that was not a fork of the authoring session.
- **It has been used again since it was forged.** At least one later invocation that did
  the job, in real work, not a rehearsal.

This was an open question and it is now settled at "both". An unproven skill costs a
reviewer more than it saves them: they have to reconstruct the evidence the author never
gathered, and a skill that no one has re-run is a guess about the future dressed up as a
capability. If only one condition holds, keep the skill local and revisit later.

If the skill misfired and you are here to repair it, you want `skill-compounder` section
3, not this.

## 1. Preflight the skill (read-only)

```bash
skillcontrib preflight ~/.claude/skills/<name>
```

`skillcontrib` ships in this repo's `bin/` and the installer links it into
`~/.local/bin`. If the command is not found, that directory is not on `PATH`; call it by
full path instead (`~/claude-skill-compounder/bin/skillcontrib`) rather than skipping the
check.

Hard failures are the things that break loading: frontmatter that does not parse, a
missing `name` or `description`, a key outside the six portable ones (`name`,
`description`, `license`, `compatibility`, `metadata`, `allowed-tools`), or a description
past the cap the upstream validator enforces. House guidance (a description over 500
characters, a body over 500 lines) prints as a warning and does not fail, because real
shipping skills exceed both. Add `--strict` when you want the guidance enforced.

Two things this surfaces that matter later:

- **Quote the description.** An unquoted `: ` inside it makes the whole frontmatter fail
  to parse as YAML. The skill then loads with empty metadata and silently never fires,
  which is worse than a loud error. Preflight fails on this; CI's
  `claude plugin validate --strict` fails on it too.
- **The file list.** Preflight prints every other file in the skill directory. Those
  travel with the skill. A procedure that copies only `SKILL.md` silently drops
  `scripts/`, `references/`, `examples/`, and `LICENSE.txt`.

## 2. Identity and path (read-only)

```bash
skillcontrib whoami --repo <owner>/<repo>
```

It prints the acting account, its permission level on the repo, whether the upstream is
archived (exit 18 if it is: stop, archived repos reject writes), and one of two roles:

- **`maintainer`**: permission is `admin`, `write`, or `maintain`. Forking is wrong here.
  It creates a redundant fork of a repo the user can already write to, and it confuses
  the review.
- **`contributor`**: anything else. Fork path.

Two identity traps worth naming out loud before you rely on the answer:

- The bare `collaborators/<user>` endpoint answers 204 for **any** collaborator, read-only
  and triage ones included, who cannot push at all. `skillcontrib` uses the permission
  endpoint instead, which distinguishes them. If you check by hand, do the same.
- `gh` acts as `GH_TOKEN` when that variable is set, which may be a different account
  from the one `gh auth status` reports and a different one again from whatever the git
  credential helper uses to upload a branch. `skillcontrib whoami` warns when the
  variable is set. Resolve the discrepancy before section 5; do not hope they match.

These two roles are two different procedures in section 5, not one procedure with a
footnote.

## 3. Duplicate check (read-only)

```bash
skillcontrib dedup <skill-name> --description "<the description, verbatim>" \
  --repo <owner>/<repo>
```

Three probes, cheapest first, because no single key is both precise and complete:

|Probe|Question|Catches|Misses|
|-|-|-|-|
|tree|Does `skills/<name>/` already exist upstream, and what does its frontmatter declare as `name`?|A skill that already ships. This is the common case and no pull request search finds it|A shipped skill under a different directory name|
|files|Does any pull request, in any state, ADD `skills/<name>/SKILL.md` outright?|Literal proposals, open, merged, or declined|The same idea proposed under a different name|
|fuzzy|Do the description's tokens overlap pull request titles?|Renamed duplicates|Nothing, but it produces real false positives|

The exit code is the whole contract:

|Code|Meaning|What to do|
|-|-|-|
|0|Nothing found|Proceed to section 4|
|3|Mentions, touches, or fuzzy hits|**Ask the user.** Show every row. Never decide alone|
|4|A pull request that proposed this skill is OPEN or MERGED|Stop. It already exists|
|5|A pull request that proposed this skill was CLOSED without merging|Stop. A maintainer declined this|
|9|`skills/<name>/` already exists upstream|Stop. Improve the existing skill instead|
|18|Upstream is archived|Stop. Find the successor repo|

Exit 5 is the one that matters most, and it is deliberately hard to trigger: it requires
the pull request to have **added** the skill file wholesale, not merely mentioned or
edited it. A typo fix inside an existing skill is reported as a `touch`, not a rejection.
That distinction is what keeps `--override-rejected` meaningful. When exit 5 does fire,
show the user the pull request's number, title, and URL and let them read the review
before anything else happens. Only if they then say to proceed do you re-run with
`--override-rejected`, which downgrades the block to a question rather than silencing it.
Never pass that flag on your own judgment.

Three limits of the lookup, to state to the user rather than paper over:

- The pull request probes read GitHub's **search index**, which lags creation by seconds
  to minutes. A duplicate opened moments ago can be invisible. Absence of evidence here
  is not evidence of absence.
- The fuzzy probe scores token overlap against titles. It flags unrelated work that
  shares vocabulary. Rows below the threshold are printed but not counted, so read the
  list rather than only the exit code.
- These queries drain the **graphql** budget, not the search one. Check
  `gh api rate_limit --jq .resources.graphql` if calls start failing.

## 4. Consent gates. Nothing has been written yet, and nothing may be

Every gate is required. Do not compress them into one prompt, and do not proceed on
silence or on an ambiguous "sounds good". Walk them in order and show the actual output.

- **G1. Identity and target.** Print the `skillcontrib whoami` output verbatim, including
  any token warning. The user sees whose account this goes out under and against which
  repo.
- **G2. Full dedup result.** Print every row `skillcontrib dedup` returned, the
  sub-threshold ones included, plus the exit code and what it means. The user can
  overrule the tool either way.
- **G3. State the path out loud.** Say "maintainer path: branching directly on upstream"
  or "fork path: forking to `<user>/<repo>`". Name the fork's owner; an `--org` value
  would change it.
- **G4. Show the change, locally.** Stage the skill in a local clone and show
  `git status --short` and `git diff --cached --stat`, plus the branch name and the commit
  message. All of this is local. Nothing has been uploaded.
- **G5. Show the pull request text, locally.** Write the filled-in
  `.github/PULL_REQUEST_TEMPLATE.md` to `pr-body.md` in the clone and print it, along with
  the exact command that will open the pull request: repo, base, head, title, body file.
  Do **not** reach for `--dry-run` here. Its own help says "May still push git changes",
  so it is not a read-only preview and it does not belong before consent.
- **G6. Explicit go-ahead.** Ask as a distinct question and wait for a distinct answer.

Three standing prohibitions:

- **Never auto-retry over a detected rejection.** Exit 5 stops the run. The user decides.
- **Never escalate token scopes.** If a scope is missing, print the exact command for the
  user to run themselves (`gh auth refresh -s repo`) and stop. Do not start an auth flow
  they did not ask for.
- **Never open a pull request whose body and target the user has not read.** It is a
  public, identity-attributed write, and closing one still leaves the record.

## 5. The write sequence. Every step here is a network write

Do not enter this section until G6 returned yes. Each step is labeled W because each one
is visible to other people.

### 5a. Maintainer path (role: `maintainer`)

- **W1.** Clone upstream and branch:
  `git clone https://github.com/<owner>/<repo>.git`, then
  `git switch -c add-skill-<name>`.
- **W2.** Copy the **whole** skill directory, not just its SKILL.md:
  `mkdir -p skills/<name> && cp -R ~/.claude/skills/<name>/. skills/<name>/`, then
  `git add skills/<name>` and `git commit -m "Add <name> skill"`.
- **W3.** Upload the branch to `origin`, which is upstream on this path. Never commit to
  the default branch directly; the review is the point.
- **W4.** Optional: run the create command with `--dry-run` now, after the branch is
  already uploaded, where its "may still push git changes" caveat costs nothing.
- **W5.** Open the pull request from that branch with `--body-file pr-body.md`.

### 5b. Fork path (role: `contributor`)

- **W1.** `gh repo fork <owner>/<repo> --clone --remote`. This creates a repository under
  the user's account: a network write, and the first one. `origin` becomes the fork,
  `upstream` the original.
- **W2.** If the fork already existed and is behind, `gh repo sync <user>/<repo>` before
  branching. **This is a write too**, not a check: it fast-forwards the fork. A branch cut
  from a stale fork produces a diff full of other people's reverts.
- **W3.** Branch and copy the whole directory, exactly as in 5a W1 and W2.
- **W4.** Upload the branch to `origin`, the fork, never upstream.
- **W5.** Open the pull request against upstream with an explicit cross-repo head:

```bash
gh pr create --repo <owner>/<repo> --head <your-user>:add-skill-<name> \
  --title "Add <name> skill" --body-file pr-body.md
```

Every flag above exists in the installed `gh`. `pr-body.md` is the file written at G5;
if it does not exist, you skipped a gate. Fill it from
`.github/PULL_REQUEST_TEMPLATE.md`: red-team rounds and their findings, the trigger
prompts, the fixture, and the local-reuse evidence. Evidence that is not in the body is
evidence the reviewer has to go find, and the contribution stalls.

## Failure modes

|Symptom|Detect (read-only)|Response|
|-|-|-|
|`skillcontrib` not found|`command -v skillcontrib`, rc 127|Call it by full path from this repo's `bin/`. Do not skip the check|
|`gh` not installed|`command -v gh`; `skillcontrib` exits 6|Stop. Tell the user to install it. Do not hand-roll the REST calls|
|Not authenticated|`gh auth status`; `skillcontrib` exits 7|Stop. The user runs `gh auth login` themselves|
|Missing token scope|403 on the first write; the scopes line of `gh auth status`|Stop and print `gh auth refresh -s repo`. Never run it for them|
|Token identity mismatch|`GH_TOKEN` set; `skillcontrib whoami` warns|Resolve before W1. The pull request and the commits can otherwise land under different accounts|
|Read-only collaborator|`gh api repos/<r>/collaborators/<u>/permission`|`read` or `triage` is the fork path. The bare 204 check would call it a maintainer and be wrong|
|Fork already exists|`gh repo view <user>/<repo> --json isFork,parent`|Reuse it, and sync it at 5b W2. Do not create a second one|
|Fork stale behind upstream|Compare the fork's default-branch SHA to upstream's|`gh repo sync`, inside the write sequence, never before the gates|
|Branch name collision|`gh api repos/<user>/<repo>/branches/<name>` returns 200, not 404|Suffix the branch (`add-skill-<name>-2`). Never force-update someone's branch|
|Upstream archived|`skillcontrib whoami` or `dedup` exits 18|Stop. Find the successor repo|
|Rate limited|`gh api rate_limit --jq .resources.graphql`|Wait for the reset it names. These queries drain graphql, not search|
|Dedup lookup failed|`skillcontrib` exits 8|A failed lookup is not a clean one. Fix it, or stop|

## Traps that produce a confidently wrong answer

- **A pull request search alone misses skills that already ship.** Check the tree. The
  pull request that added a skill may predate the search window or never name it in the
  title. This is the failure that makes a whole dedup layer look like it works when it
  does not.
- **`--limit 100` is load-bearing.** The default page size is 30, so a sweep without it
  silently misses older pull requests and reports "no duplicate".
- **`gh api search/issues -f q=...` answers 404.** Passing `-f` flips `gh api` to POST,
  and `POST /search/issues` does not exist. If you need the search API for a qualifier
  `gh pr list --search` does not expose, it must be `-X GET`.
- **`repos/<r>/pulls?state=all` has no text search.** Filtering it means paginating
  everything and matching client-side. A fallback, not a default.
- **A merged pull request is a closed one.** Read the JSON `state` field, which separates
  `MERGED` from `CLOSED`, not the open/closed distinction.
- **`gh pr create --dry-run` is not read-only.** Its help says it may still push git
  changes. It belongs after the go-ahead, not before it.
