D1. Choose (c): keep the trust boundary, but make replacement explicit.

A project guard should not suppress a general guard; the contract explicitly prevents repository files from taking the place of shipped advice (docs/design.md:345–353). However, the current implementation suppresses every matching general guard whenever any user guard matches, which can hide unrelated advice in a compound command (bin/compound:3232–3238). I would require a user-controlled declaration that a particular user lesson replaces a particular general lesson; otherwise, quote both in one refusal.

Main risk: extra configuration and duplicate advice until replacements are declared.
Confidence: high.

D2. Keep shadowing; do not add blanket per-repository override or rename-on-load.

The refusal claim is keyed by lesson name, so letting project content reuse a trusted name can consume its refusal before the intended guard fires (hooks/register.ts:1030–1035). Shadowing prevents that, preserves the original identity, and exposes the collision rather than silently manufacturing a new name (bin/compound:1548–1552; docs/design.md:119–127). Resolve legitimate collisions through an explicit rename on disk; repository trust should not silently change what an existing lesson name means.

Main risk: a legitimate project lesson becomes inactive following a collision, including one introduced by a package update.
Confidence: high.

D3. Keep rejection of invalid or mismatched names.

The loader checks both the directory slug and its equality with the frontmatter name, then excludes malformed lessons while reporting the problem (bin/compound:1352–1359, 1526–1535). Sanitisation is ambiguous: different names can collapse to one slug, and the displayed name can cease to identify the directory that update/remove commands address. Offer an explicit repair operation if needed, with a proposed name and collision check, rather than changing identity during loading.

Main risk: harmless hand-editing mistakes temporarily disable useful lessons.
Confidence: very high.

D4. Keep the publication refusal with no override flag.

This command publishes to a repository, and the current check rejects recognised credential shapes before cloning or pushing (bin/compound:3547–3565, 3601–3627). For this convenience workflow, replacing a realistic credential example with a conspicuous placeholder is preferable to teaching the model a flag that bypasses the protection. The contract correctly describes detection as a lower bound, so a passing scan must not imply that publication is safe (docs/design.md:649–654).

Main risk: legitimate security examples or fixtures may require rewriting or a separate manual contribution.
Confidence: high.

D5. Choose (b): restrict production log events; seed fixtures through a test helper.

Small correction: log already rejects unknown event types, but accepts recognised settlement events and supplied session/project values (bin/compound:3764–3777). Reserve learn, skip, rm, skill and promote events for the commands that perform those operations; put arbitrary fixture insertion in a repository test helper that requires an isolated store. This improves event integrity without pretending to stop a hostile same-user process: that process can edit the log directly, and the contract explicitly trusts it (docs/design.md:670–673). Signing events would add machinery without establishing a useful boundary while the same execution environment controls the files and credentials.

Main risk: test migration and maintenance work, with no protection against deliberate same-user tampering.
Confidence: high.

D6. Choose (b): exempt only a conservatively recognised single compound invocation.

The implementation is broader than the example: cliCall searches every simple command, so even “anything; compound list” exempts the entire call (hooks/render.ts:212–218). That also skips failure recall and capture, not just guards (hooks/register.ts:1492–1499, 1535–1537). Preserve the exemption for lesson-writing commands, whose literal arguments legitimately contain guarded examples, but reject executable composition, substitutions, backticks and process substitutions from exemption eligibility; ambiguous syntax should receive normal checking.

Main risk: legitimate multiline or composed lesson-writing commands receive nuisance refusals; --body-file provides a straightforward alternative.
Confidence: high.

D7. Choose (b): make it recall-only.

The lesson already has a failure-specific description, whereas its guard uses only command text plus platform and explicitly acknowledges that an installed timeout makes its refusal wrong (lessons/macos-gnu-only-commands/SKILL.md:3–5, 23–24). A shipped lesson should not interrupt a valid command every session merely because stock macOS lacks the program. A PATH condition evaluated in the CLI would introduce another environment approximation—especially for inline PATH changes or nested shells—without enough benefit to justify a general condition mechanism here.

Main risk: the first genuinely missing-command failure happens before advice arrives.
Confidence: high.

D8. Choose (a): at most one qualifying recurrence per lesson revision per session.

Keep every recall event for reporting, but deduplicate the count used to demand strengthening; currently tally counts individual events, and the hook independently predicts the threshold with “since + 1” (bin/compound:1777–1797; hooks/register.ts:1097–1120). Move that eligibility decision into one authoritative CLI operation so parallel hooks cannot disagree about whether this recall counts. A time window is arbitrary, while “the same agent already saw it” measures a different question: repeated failures across sessions can still justify adding a preventive guard even when each new agent first receives the lesson after failing.

Main risk: repeated sequential mistakes in one long session will trigger strengthening later than they otherwise would.
Confidence: medium-high.

D9. An unchanged retry that succeeds is not, by itself, a fix worth capturing.

The judge’s existing rule requires a mistake in how the call was written and a reusable lesson that prevents it; a fail/pass pair alone establishes neither (hooks/judge.ts:173–183). Return NONE for a bare retry, and close the held episode as recovered without creating lesson debt, rather than leaving it available to match an unrelated later success. Do not equate identical command text with unchanged circumstances: an intervening installation or configuration correction could be a real fix, but the current judge receives only the failed call, error and successful call, so it lacks that evidence (hooks/register.ts:1181–1184). Capture retry guidance only with evidence supporting a specific, bounded, safe retry procedure—not a single lucky rerun.

Main risk: some useful transient-failure workarounds will require manual capture or richer evidence.
Confidence: high.

Other owner decisions

- Publication scanning versus publication guarantees: attachment scanning stops at 1 MiB and ignores read errors, while publication later copies whole files from the source (bin/compound:3376–3384, 3609–3615). I recommend scanning a frozen staging tree in full and publishing those exact bytes, refusing unreadable inputs.
- Settlement scope: one later learn or skip settles every earlier capture from the same session, regardless of which problem it addresses (bin/compound:1879–1883). Decide whether that should require explicit capture IDs, particularly with parallel agents.
- Lesson identity: distinct project lessons may share a name, but recurrence accounting is keyed only by name (docs/design.md:111–113; bin/compound:1777–1797). Use level/project identity plus a content revision so unrelated lessons cannot affect one another’s counts.
- Held failures: recalling a lesson for a new failure unconditionally deletes the agent’s earlier held failure (hooks/register.ts:1163–1169). Preserve the earlier unresolved episode; the tracker already records a lost capture from this behaviour (notes/2026-10-04-audit-work-tracker.md:126–129).

