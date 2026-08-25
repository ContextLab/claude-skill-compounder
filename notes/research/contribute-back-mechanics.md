# Contribute-back mechanics: verified findings

Date: 2026-08-24. All commands below were actually executed with `gh` 2.60.1,
authenticated as `jeremymanning` (scopes: admin:org, gist, project, repo, workflow).
No fork, push, or PR was created — every command was read-only. Test target for
dedup-search mechanics was `cli/cli` (chosen because it has thousands of PRs in
open/closed/merged states, unlike the target repo `ContextLab/claude-skill-compounder`,
which currently has no PRs at all).

## 1. Dedup search — which `gh` invocation is authoritative

### Candidate A: `gh pr list --state all`

```
$ gh pr list --repo cli/cli --state all --limit 5 --json number,title,state,headRefName
[{"headRefName":"fix/namespaced-skill-file-tree","number":14254,"state":"OPEN", ...}]

$ gh pr list --repo cli/cli --state closed --limit 5 --json number,title,state
[{"number":14241,"state":"CLOSED", ...}, {"number":14222,"state":"MERGED", ...}]

$ gh pr list --repo cli/cli --state merged --limit 5 --json number,title,state
[{"number":14222,"state":"MERGED", ...}, ...]
```

Verified: `--state all` really does return OPEN, CLOSED, and MERGED items together
(GitHub represents "merged" as a closed PR with `merged_at` set; the `state` JSON
field shows `MERGED` distinctly). `--state merged` also works as a value, even
though it isn't documented in `gh pr list --help`'s flag description (undocumented
but functional passthrough to the underlying GraphQL enum).

Content search via `gh pr list --search`:

```
$ gh pr list --repo cli/cli --state all --search "extension" --limit 5 --json number,title,state
[{"number":13982,"state":"OPEN","title":"Add --latest-pre-release and --pin flags to gh extension upgrade"},
 {"number":13602,"state":"OPEN", ...}, {"number":14178,"state":"OPEN", ...},
 {"number":14072,"state":"MERGED", ...}, {"number":14131,"state":"CLOSED", ...}]
```

`--search` is passed straight to GitHub's search API under the hood (same engine
as `gh api search/issues`), so it supports full qualifiers (`is:pr`, `in:title`, etc.)
and returns closed/merged hits.

**Default page size**: `gh pr list --repo cli/cli --state all --json number` with no
`--limit` returned exactly 30 records — confirms the default limit is 30 and must be
raised explicitly for a real dedup sweep (`--limit 100` etc., or loop with `gh api
--paginate`).

### Candidate B: `gh api search/issues -f q=...`

```
$ gh api search/issues -f q='repo:cli/cli is:pr extension'
{"message":"Not Found","documentation_url":"https://docs.github.com/rest","status":"404"}
```

This 404 is a **gh footgun, not a real API limitation**: passing `-f` fields makes
`gh api` default to `POST`, and `POST /search/issues` doesn't exist. Verified via
`--verbose`: request line was `POST /search/issues HTTP/1.1`. Fix is `-X GET`:

```
$ gh api search/issues -X GET -f q='repo:cli/cli is:pr extension' --jq '.total_count'
260

$ gh api search/issues -X GET -f q='repo:cli/cli is:pr extension' --jq '.items[] | {number, title, state}' | head
{"number":13982,"state":"open", ...}
{"number":14072,"state":"closed", ...}
{"number":14131,"state":"closed", ...}
... (open, closed, and previously-merged-now-closed items interleaved)
```

With `-X GET` this is the same underlying search index `gh pr list --search` uses,
confirmed by overlapping result sets between the two commands above. Adding
`is:closed` further narrows correctly:

```
$ gh api search/issues -X GET -f q='repo:cli/cli is:pr is:closed extension' --jq '.items[] | {number,title,state}'
(20 results shown, all state:"closed", including merged-then-closed PRs)
```

Rate limit for this endpoint, confirmed via `gh api rate_limit`:

```
$ gh api rate_limit --jq '.resources.search, .resources.core'
{"limit":30,"remaining":30,"reset":1787627043,"used":0}   <- search: 30/min
{"limit":5000,"remaining":4999,"reset":1787627168,"used":1} <- core: 5000/hr
```

Known GitHub-documented (not independently re-verified here, since it requires
observing a just-created PR) limits on this endpoint: results capped at 1000 total
per query, and the search index can lag live PR state by seconds to low minutes
after a PR is opened/closed — meaning a dedup check run immediately after another
user's PR merge can theoretically miss it.

### Candidate C: `gh api repos/<r>/pulls?state=all`

```
$ gh api "repos/cli/cli/pulls?state=all&per_page=5" --jq '.[] | {number,title,state,merged_at}'
{"merged_at":null,"number":14254,"state":"open", ...}
...
```

This is the plain REST "List pull requests" endpoint. Confirmed it takes a `state`
filter but **has no full-text search parameter** — filtering by title content
requires pulling all pages and grep/jq-filtering client-side:

```
$ gh api "repos/cli/cli/pulls?state=all&per_page=100" \
    --jq '[.[] | select(.title | test("extension";"i"))] | length'
3
```

That is real content matching but done locally after fetching, not server-side —
expensive at scale (would need `--paginate` across potentially thousands of PRs) and
subject to core rate limit (5000/hr), not the tighter search limit.

### Recommendation

**Use `gh pr list --repo <upstream> --state all --search "<term>" --json number,title,state,url,headRefName --limit 100`**
as the primary dedup lookup, falling back to `gh api search/issues -X GET -f
q='repo:<upstream> is:pr <term>'` when you need qualifiers `gh pr list --search`
doesn't expose (e.g. `in:title`). Both are backed by the GitHub search index, so
they share its limits:
- 30 requests/min (authenticated) rate limit — much tighter than the 5000/hr REST
  core limit, so don't loop it per-file.
- Results capped at 1000; fine for this use case (a seed-pool repo will never have
  that many PRs).
- Search-index lag is a real, GitHub-documented risk: a PR opened/merged seconds ago
  may not yet be indexed. Mitigate by also doing one unindexed, authoritative check —
  `gh pr list --state all --json headRefName,title` without `--search`, scanning
  all pages — as a belt-and-suspenders pass when the search-based check comes back
  clean, since that path reads live PR state, not the search index.
- `repos/<r>/pulls` (REST) is reliable and unaffected by search-index lag, but has
  no server-side content search, so it's a reasonable fallback ONLY if you're
  willing to paginate and filter client-side with jq — verified to work but not the
  best default because of manual pagination and the extra round trips.

## 2. Dedup key recommendation

Three candidate keys observed in this repo's own skill structure
(`/Users/jmanning/claude-skill-compounder/skills/skill-compounder/SKILL.md`):

```
---
name: skill-compounder
description: Use when deciding whether a repeatable procedure should become a reusable skill, ...
---
```

- **Skill directory name** (e.g. `skills/skill-compounder/`): trivial to check
  (`git ls-tree` on the PR's `headRefName`, or `files` from `gh pr list --json files`),
  but two different contributors proposing "the same idea" will very plausibly choose
  different directory names (`pr-dedup-checker` vs `contribute-back-verifier`).
  False-negative risk is HIGH.
- **`name:` frontmatter field**: same problem — it's author-chosen prose, not a
  content hash. Two authors independently building the same capability will pick
  different names more often than not. False-negative risk is HIGH; false-positive
  risk is near zero (an exact string match on `name:` is meaningful when it hits).
- **Content hash of SKILL.md body**: false-positive rate near zero, but false-negative
  rate is effectively 100% for anything but a byte-identical resubmission — any
  rewording, reordering, or added example defeats it entirely. Nearly useless alone.
- **Fuzzy title/description match** against PR titles and existing skill
  descriptions (e.g. token-overlap or embedding similarity between the new skill's
  `description:` and every open/closed/merged PR's title + the description of every
  skill already merged into `skills/`): catches the "same idea, different name" case
  that directory/name/hash all miss.

**Recommendation: layer two checks, not one.**
1. Exact-match gate (cheap, precise): directory name AND `name:` frontmatter,
   case-insensitive, against `files` from every PR (any state) and every directory
   already in `skills/` on `main`. This never fires on a genuinely different skill
   (false-positive rate ~0), but only catches literal resubmissions or renames of the
   identical skill (so it under-catches "same idea, new name").
2. Fuzzy-match advisory gate (recall-oriented, imprecise): compare the new skill's
   `description:` frontmatter against the title + `description:`/body of every
   existing PR (open/closed/merged) and every merged skill, surfacing anything above
   a similarity threshold as "possible duplicate — human should look before opening
   a PR." This will have real false positives (two skills that both mention "GitHub"
   and "pull request" but do unrelated things) — so it must gate a **prompt to the
   user**, never a silent auto-abort, and it must never gate a silent auto-submit either.

**On rejected (closed, unmerged) PRs specifically**: treat a closed-and-unmerged PR
touching a matching directory/name as a stronger signal than an open one — it means
a maintainer already looked at this exact contribution and declined it. The skill
must show the user that closed PR's title, number, and URL and require an explicit
"propose anyway" confirmation rather than silently retrying it, since the rejection
reason (as opposed to the mere existence of a PR) is not machine-readable without
also fetching and summarizing the PR's review comments.

**Honest summary**: no available key is both high-precision and high-recall.
Exact-match under-catches (misses same-idea-different-name); fuzzy-match
over-catches (flags genuinely distinct skills that share vocabulary). The
recommended combination is safe by design because the imprecise layer only ever
produces a question to the human, never an autonomous decision.

## 3. Fork + PR sequence — flags verified against installed `gh` 2.60.1

```
$ gh --version
gh version 2.60.1 (2024-10-25)
https://github.com/cli/cli/releases/tag/v2.60.1
```

`gh repo fork --help` (verified flags exist, quoted verbatim):

```
FLAGS
  --clone                 Clone the fork
  --default-branch-only   Only include the default branch in the fork
  --fork-name string      Rename the forked repository
  --org string            Create the fork in an organization
  --remote                Add a git remote for the fork
  --remote-name string    Specify the name for the new remote (default "origin")
```

Note: help text names the flag `--clone`, not `--clone` combined into one string
`fork --clone` as sometimes written elsewhere — confirmed this is the real,
current flag name in 2.60.1 (some older docs online show a different default
remote-naming behavior; this help text is authoritative for the installed version).

`gh pr create --help` (verified flags exist, quoted verbatim, relevant subset):

```
FLAGS
  -B, --base branch          The branch into which you want your code merged
  -b, --body string          Body for the pull request
  -d, --draft                Mark pull request as a draft
      --dry-run              Print details instead of creating the PR. May still push git changes.
  -H, --head branch          The branch that contains commits for your pull request (default [current branch])
  -t, --title string         Title for the pull request
INHERITED FLAGS
  -R, --repo [HOST/]OWNER/REPO   Select another repository using the [HOST/]OWNER/REPO format
EXAMPLES
  $ gh pr create --base develop --head monalisa:feature
```

This confirms the `owner:branch` form for `--head` and `--repo <upstream>` for
targeting the upstream repo from a fork are both real, documented, current flags —
exactly the form needed to open a PR against `ContextLab/claude-skill-compounder`
from a personal fork's branch without `cd`-ing into the fork.

### Recommended real sequence (NOT executed — dry run only, written from verified flags)

```bash
# 1. Fork + clone in one step (creates ~/.../claude-skill-compounder fork under the
#    user's account, clones it locally, sets origin=fork / upstream=ContextLab)
gh repo fork ContextLab/claude-skill-compounder --clone --remote

# 2. Work on a uniquely named branch (avoid collisions — see failure modes)
cd claude-skill-compounder
git checkout -b add-skill-<skill-dir-name>

# 3. Add the skill, commit
git add skills/<skill-dir-name>
git commit -m "Add <skill-dir-name> skill"

# 4. Push to the fork (origin), not upstream
git push -u origin add-skill-<skill-dir-name>

# 5. Open the PR against the upstream repo explicitly, from fork:branch
gh pr create --repo ContextLab/claude-skill-compounder \
  --head <github-username>:add-skill-<skill-dir-name> \
  --title "Add <skill-dir-name> skill" \
  --body "<what it does, why, dedup check performed>"
```

`--dry-run` on `gh pr create` was confirmed to exist in this version's help text
and should be used as the last pre-flight step before the real create call (see
consent gates below).

## 4. Failure modes

| Failure mode | How to detect (read-only) | Real evidence obtained |
|-|-|-|
| `gh` not installed | `command -v gh` / `which gh` | `which gh` → `/opt/homebrew/bin/gh` on this machine; absence gives shell "command not found" |
| `gh` not authenticated | `gh auth status` | Ran and got success: `✓ Logged in to github.com account jeremymanning`; an unauthenticated run instead errors `You are not logged into any GitHub hosts. Run gh auth login to authenticate.` (documented `gh` behavior) |
| Token lacking scopes | `gh auth status` scopes line | Verified current token scopes: `'admin:org', 'gist', 'project', 'repo', 'workflow'` — `repo` is present and sufficient for fork/push/PR; a token missing `repo` (or `public_repo` for a public target) gets an HTTP 403 on fork/push, and `gh pr create --project` would additionally need the `project` scope, which is present |
| Fork already exists | `gh repo view <user>/<repo> --json isFork,parent` | Ran against `jeremymanning/claude-skill-compounder` (doesn't exist yet): got `GraphQL: Could not resolve to a Repository with the name 'jeremymanning/claude-skill-compounder'.` — proves no fork currently exists for this user; when one exists this call instead returns `isFork:true` and `parent.owner.login` |
| Fork exists but stale behind upstream | Compare `gh api repos/<user>/<repo>` `pushed_at`/default branch SHA against `gh api repos/<upstream>/<repo>` default branch SHA (or `gh repo sync --dry`) | Not directly testable here (no fork exists yet); the mechanism is real and documented (`gh repo sync <user>/<repo>` fast-forwards a fork) |
| Branch name collision | `gh api repos/<user>/<repo>/branches/<name>` returns 404 if free | Not run against a real collision (no fork/branch exists), but the `collaborators/<user>` call above demonstrated the same 404-vs-204 pattern gh uses for existence checks — a 200 on this endpoint means the branch name is taken and a suffix (skill dir + short hash, or a timestamp) is needed |
| Upstream archived | `gh repo view <upstream> --json isArchived` | Ran for real: `{"isArchived":false, ...}` — confirms `ContextLab/claude-skill-compounder` is currently writable; an archived repo returns `isArchived:true` and rejects forks/pushes with a 403 |
| Rate limited | `gh api rate_limit` | Ran for real: core 5000/hr (4999 remaining), search 30/min (30 remaining) at test time — plenty of headroom for this workflow, which needs only a handful of calls |
| User is a maintainer of upstream (fork unnecessary) | `gh api repos/<upstream>/collaborators/<user>` (204 = yes, 404 = no) | Ran for real against `ContextLab/claude-skill-compounder` / `jeremymanning`: **HTTP 204 No Content — jeremymanning already has collaborator/write access.** This is a genuinely surprising, real finding: for this specific user and repo, forking is unnecessary and the skill should detect this and offer to push a branch directly to upstream and open the PR from there instead of forking, since forking one's own accessible repo is pointless and would confusingly create `jeremymanning/claude-skill-compounder` as a redundant fork of a repo they already have push rights to |

## 5. Consent and safety gates required before any network write

Given the real finding above (this user is already a maintainer of the seed repo,
so the "fork" step is a decision point, not a given), the skill must, in order:

1. **Show, don't assume, identity and target.** Print the authenticated `gh auth
   status` account and the exact upstream repo (`ContextLab/claude-skill-compounder`)
   before doing anything else, so the user isn't surprised by whose name the PR
   goes out under.
2. **Run and display the dedup check's full result before proposing to act** —
   list every matching open/closed/merged PR found (number, title, state, URL) from
   both the exact-match and fuzzy-match passes (section 2), even the ones below
   threshold, so the user can override the tool's judgment either way (skip because
   it's clearly not a dup, or hold back because the tool missed an obvious one).
3. **Explicit maintainer-status branch.** Since collaborator status changes the
   whole plan (branch on upstream vs. fork), surface which path it detected and why
   (204 vs. 404 on the collaborators check) and require confirmation before
   proceeding down that path — do not silently choose.
4. **Show the fork name/target org before creating it** (`--org` changes ownership
   of the new fork) and confirm no fork already exists (or that the existing one
   will be reused/synced, not recreated).
5. **Show the exact diff/file list that will be committed** (`git diff --stat`,
   `git status`) and the exact commit message and branch name before `git push`.
6. **Dry-run the PR first.** Use `gh pr create --dry-run` to show the title, body,
   base, and head that would be used, and require a final explicit go-ahead before
   dropping `--dry-run` and actually opening the PR — this is the actual
   internet-visible, identity-attributed write, and it cannot be undone by the tool
   (closing a PR still leaves a public record under the user's account).
7. **Never auto-retry past a detected rejection.** If the dedup check surfaced a
   closed-unmerged PR for the same/similar skill, block auto-submission entirely
   and require the user to read that PR's outcome and affirmatively choose to
   proceed anyway (per section 2).
8. **No silent scope escalation.** If a required scope (e.g. `repo`) is missing,
   stop and tell the user to run `gh auth refresh -s repo` themselves — never invoke
   an auth flow on the user's behalf without them seeing what scope is being
   requested and why.

## Files referenced

- `/Users/jmanning/claude-skill-compounder/skills/skill-compounder/SKILL.md` (frontmatter convention: `name:`, `description:`)
- `/Users/jmanning/claude-skill-compounder` git remote: `https://github.com/ContextLab/claude-skill-compounder.git`
