#!/usr/bin/env python3
"""Tests for hooks/doc-gate.sh -- the PreToolUse gate that refuses a `git push`
carrying code changes and no documentation change.

NO MOCKS, per this repo's standing rule, and here that rule has real teeth: the gate's
whole answer comes out of `git rev-list @{u}..HEAD`, so a test that faked git would be
testing nothing at all. Every test below builds a REAL repository in a temp directory
with a REAL local bare remote, pushes an initial commit so that `@{u}` genuinely
resolves, and then makes real commits ahead of it. The hook is run as a real process
with a minimal PATH, a temp HOME and SKILL_COMPOUNDER_STATE pinned into the temp tree,
and its decision is read off stdout and parsed as JSON.

EVERY subprocess call against the hook passes `input=`. The script reads its payload with
`payload="$(cat)"`; without stdin it hangs forever. Every `git` call passes
`stdin=DEVNULL` for the same reason -- git can open an editor or a credential prompt.

THE PAYLOAD SHAPE IS THE MEASURED ONE. `PreToolUse` keys, recorded on Claude Code
2.1.245 and written up in docs/CLAUDE-CODE-BEHAVIOR.md: cwd, effort, hook_event_name,
permission_mode, prompt_id, session_id, tool_input, tool_name, tool_use_id,
transcript_path. A deny is
`{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny",
"permissionDecisionReason":"…"}}` on stdout with exit status 0.
"""

import json
import os
import pathlib
import re
import shutil
import subprocess
import tempfile
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOK = os.path.join(REPO, "hooks", "doc-gate.sh")

# Minimal, explicit environment: the script must not depend on the ambient one.
BASE_PATH = "/usr/bin:/bin:/usr/sbin:/sbin:/usr/local/bin:/opt/homebrew/bin"


def hook_text():
    with open(HOOK, encoding="utf-8") as fh:
        return fh.read()

# Pinned clock, so an override row's timestamp is checkable rather than "about now".
# THIS SCRIPT'S OWN CLOCK. Pinning CI_NOW or SKILLFORGE_NOW would do nothing here, which
# is the point of the per-script rule in .claude/CLAUDE.md.
NOW = "1787788800"


class DocGateTest(unittest.TestCase):

    # ----------------------------------------------------------------- real fixtures
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="docgate-")
        self.home = os.path.join(self.tmp, "home")
        self.state = os.path.join(self.tmp, "state")
        self.remote = os.path.join(self.tmp, "remote.git")
        self.repo = os.path.join(self.tmp, "work")
        os.makedirs(self.home)
        os.makedirs(self.state)

        # A committer identity through the environment rather than `git config`, so no
        # global config is read or written and HOME can stay an empty temp directory.
        self.gitenv = {
            "PATH": BASE_PATH,
            "HOME": self.home,
            "GIT_AUTHOR_NAME": "Doc Gate Test",
            "GIT_AUTHOR_EMAIL": "docgate@example.invalid",
            "GIT_COMMITTER_NAME": "Doc Gate Test",
            "GIT_COMMITTER_EMAIL": "docgate@example.invalid",
            "GIT_CONFIG_NOSYSTEM": "1",
        }

        self.git("init", "--bare", "-q", self.remote, cwd=self.tmp)
        self.git("init", "-q", self.repo, cwd=self.tmp)
        # THE BRANCH NAME IS PINNED, and it stopped being cosmetic the moment the gate
        # started reading the refspec: `git push origin main` is only a push of the
        # current branch if the current branch IS `main`, and `git init` here produces
        # `master` (git 2.50.1, no init.defaultBranch, GIT_CONFIG_NOSYSTEM and an empty
        # HOME). `symbolic-ref` rather than `init -b`, which needs git >= 2.28.
        self.git("symbolic-ref", "HEAD", "refs/heads/main")
        self.write("README.md", "# project\n")
        self.write("hooks/a.sh", "#!/bin/sh\necho hi\n")
        self.git("add", "-A")
        self.git("commit", "-qm", "initial")
        self.git("remote", "add", "origin", self.remote)
        # `-u` is what gives HEAD an upstream, which is what `@{u}` in the hook resolves.
        self.git("push", "-q", "-u", "origin", "HEAD")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def git(self, *args, cwd=None):
        r = subprocess.run(
            ["git"] + list(args), cwd=cwd or self.repo, env=self.gitenv,
            capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=120,
        )
        self.assertEqual(r.returncode, 0,
                         "git %s failed: %s%s" % (" ".join(args), r.stdout, r.stderr))
        return r.stdout

    def dry_run(self, *args):
        """A REAL `git push --dry-run` against the REAL local bare remote, returning
        stdout AND stderr joined -- git writes its `main -> main` / `[new tag]` report to
        STDERR, so a helper that returned stdout alone would assert against an empty
        string and pass no matter what git did. Used to MEASURE, in the test, the git
        behaviour a refspec rule below is derived from, rather than restating it from
        memory. `--dry-run` writes nothing to any remote."""
        r = subprocess.run(
            ["git", "push", "--dry-run"] + list(args), cwd=self.repo, env=self.gitenv,
            capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=120,
        )
        self.assertEqual(r.returncode, 0,
                         "git push --dry-run %s failed: %s%s"
                         % (" ".join(args), r.stdout, r.stderr))
        return r.stdout + r.stderr

    def dry_run_raw(self, *args):
        """`dry_run` for the combinations git REFUSES. Some of the last-wins evidence is
        a refusal -- `--mirror --no-all origin v1.0.0` dies with "--mirror can't be
        combined with refspecs", which git could only say with `--mirror` still set -- and
        `dry_run` asserts a zero status, so it cannot carry that evidence. Returns
        (returncode, stdout+stderr) and asserts nothing."""
        r = subprocess.run(
            ["git", "push", "--dry-run"] + list(args), cwd=self.repo, env=self.gitenv,
            capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=120,
        )
        return r.returncode, r.stdout + r.stderr

    def write(self, rel, text):
        path = os.path.join(self.repo, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)

    def commit_cacheinfo(self, files, message="change"):
        """Commit paths straight into the index, bypassing the working tree.

        macOS is case-INSENSITIVE by default, so `self.write("Docs/guide.txt")` into a
        repo that already holds `docs/` lands in the existing directory and git reports
        the lowercase path -- a case test written that way passes without ever exercising
        the case it names. `git update-index --cacheinfo` writes the path as given, and
        it is the only way to be sure the gate is handed the bytes this test intends."""
        for rel, text in files.items():
            r = subprocess.run(["git", "hash-object", "-w", "--stdin"], cwd=self.repo,
                               env=self.gitenv, input=text, capture_output=True,
                               text=True, timeout=120)
            self.assertEqual(r.returncode, 0, "hash-object failed: %s" % r.stderr)
            self.git("update-index", "--add", "--cacheinfo",
                     "100644,%s,%s" % (r.stdout.strip(), rel))
        self.git("commit", "-qm", message)
        return self.git("rev-parse", "HEAD").strip()

    def commit(self, files, message="change"):
        """Write files and make one real commit ahead of the upstream."""
        for rel, text in files.items():
            self.write(rel, text)
        self.git("add", "-A")
        self.git("commit", "-qm", message)
        return self.git("rev-parse", "HEAD").strip()

    # -------------------------------------------------------------------- the hook
    def payload(self, command, session="s1", tool_use_id="tu1", cwd=None,
                event="PreToolUse", tool="Bash"):
        return {
            "hook_event_name": event,
            "session_id": session,
            "transcript_path": os.path.join(self.tmp, "transcript.jsonl"),
            "cwd": cwd if cwd is not None else self.repo,
            "prompt_id": "p1",
            "permission_mode": "acceptEdits",
            "effort": {"level": "high"},
            "tool_name": tool,
            "tool_use_id": tool_use_id,
            "tool_input": {"command": command, "description": "d"},
        }

    def run_hook(self, payload, **env_extra):
        env = {"PATH": BASE_PATH, "HOME": self.home,
               "SKILL_COMPOUNDER_STATE": self.state, "DOC_GATE_NOW": NOW}
        env.update({k: str(v) for k, v in env_extra.items()})
        body = payload if isinstance(payload, str) else json.dumps(payload)
        return subprocess.run(
            ["bash", HOOK], input=body, capture_output=True, text=True,
            env=env, timeout=180,
        )

    def push(self, command="git push", **kw):
        env_extra = {k: kw.pop(k) for k in list(kw) if k.isupper()}
        return self.run_hook(self.payload(command, **kw), **env_extra)

    # ------------------------------------------------------------------- assertions
    def decision(self, result):
        self.assertEqual(result.returncode, 0,
                         "the gate must ALWAYS exit 0; stderr=%r" % result.stderr)
        out = result.stdout.strip()
        if not out:
            return None
        return json.loads(out)

    def assert_allowed(self, result, why=""):
        d = self.decision(result)
        self.assertIsNone(d, "expected no decision%s, got %r"
                          % ((" (" + why + ")") if why else "", result.stdout))

    def assert_denied(self, result):
        d = self.decision(result)
        self.assertIsNotNone(d, "expected a deny, got nothing (stderr=%r)" % result.stderr)
        h = d["hookSpecificOutput"]
        self.assertEqual(h["hookEventName"], "PreToolUse")
        self.assertEqual(h["permissionDecision"], "deny")
        return h["permissionDecisionReason"]

    def overrides(self):
        path = os.path.join(self.state, "doc-gate", "overrides.jsonl")
        if not os.path.exists(path):
            return []
        with open(path, encoding="utf-8") as fh:
            return [json.loads(l) for l in fh if l.strip()]

    # =========================================================== the core partition
    def test_a_code_only_push_is_denied(self):
        self.commit({"hooks/a.sh": "#!/bin/sh\necho bye\n"}, "change the hook")
        reason = self.assert_denied(self.push())
        # (a) how many commits. The FULL clause, verb included: asserting only the
        # substring "1 commit" passed against "1 commit are about to leave", which is
        # what the script actually said until this assertion was tightened.
        self.assertIn("1 commit is about to leave", reason)
        # (b) the code files, in full paths
        self.assertIn("hooks/a.sh", reason)
        # (c) the skill that fixes it -- AND that the skill it names actually exists.
        # Pinning the string alone is what let this ship pointing at `documentation-sync`,
        # a skill that was pre-registered, briefed, and then deliberately never forged
        # because `claim-provenance` already owned the ground. A deny reason naming a
        # skill nobody can invoke is worse than one naming none: the session is refused
        # AND sent somewhere that does not exist.
        self.assertIn("claim-provenance", reason)
        named = re.findall(r"`([a-z][a-z0-9-]+)` skill", reason)
        self.assertTrue(named, "the reason names no skill at all")
        for skill in named:
            self.assertTrue(
                any((root / skill / "SKILL.md").is_file()
                    for root in (pathlib.Path(REPO) / "skills",
                                 pathlib.Path.home() / ".claude" / "skills")),
                "the deny reason sends the session to `%s`, which is not installed and "
                "is not in this checkout's skills/ -- a refusal that points nowhere"
                % skill)
        # (d) the exact escape hatch, both spellings
        self.assertIn("Doc-Gate-Override:", reason)
        self.assertIn("DOC_GATE_OVERRIDE=", reason)
        self.assertIn("overrides.jsonl", reason)

    def test_a_push_that_also_changes_documentation_is_allowed(self):
        self.commit({"hooks/a.sh": "#!/bin/sh\necho bye\n",
                     "README.md": "# project\n\nnow does bye\n"}, "code and docs")
        self.assert_allowed(self.push(), "a doc file is in the push")

    def test_a_documentation_only_push_is_allowed(self):
        self.commit({"README.md": "# project\n\nprose only\n"}, "docs only")
        self.assert_allowed(self.push(), "no code file in the push")

    def test_one_documentation_file_anywhere_is_enough(self):
        """Sufficiency needs a model; this gate only asks whether docs were touched."""
        self.commit({"hooks/a.sh": "#!/bin/sh\necho bye\n",
                     "docs/DESIGN.md": "one line\n"}, "code plus a doc under docs/")
        self.assert_allowed(self.push())

    def test_a_file_that_is_neither_code_nor_doc_neither_triggers_nor_satisfies(self):
        self.commit({"package-lock.json": '{"lockfileVersion": 3}\n'}, "lockfile only")
        self.assert_allowed(self.push(), "a lockfile is neither")

    def test_notes_are_not_documentation_under_the_knob(self):
        """`notes/` in THIS repository is a dated log, not a description of current
        behaviour, and counting it as documentation would let this repository's own
        pushes all pass. That argument is sound and it is repo-local, so it is now
        `DOC_GATE_NOTES=neither` rather than the default -- see the default's own test
        below, and CLASSIFICATION in the script for why the default went the other way."""
        self.commit({"hooks/a.sh": "#!/bin/sh\necho bye\n",
                     "notes/2026-08-26-session.md": "log\n"}, "code plus a note")
        reason = self.assert_denied(self.push(DOC_GATE_NOTES="neither"))
        self.assertIn("hooks/a.sh", reason)
        self.assertNotIn("notes/2026-08-26-session.md", reason)

    def test_notes_are_documentation_by_default(self):
        """ISSUE #28. The exclusion was justified by one repository's convention and
        applied to every repository the hook is installed in. Elsewhere `notes/` is
        prose, so a push carrying a note and a code file was DENIED for carrying no
        documentation, with the reason naming the note nowhere -- the one outcome this
        gate must never produce, and what the single recorded override was taken for."""
        self.commit({"hooks/a.sh": "#!/bin/sh\necho bye\n",
                     "notes/hardware/x.md": "how the rig is wired\n"},
                    "code plus a note in someone else's repository")
        self.assert_allowed(self.push(), "notes/hardware/x.md is documentation")

    def test_the_notes_default_survives_a_nonsense_setting(self):
        """A typo'd knob must reach the default, not a third behaviour, and certainly not
        the stricter branch: being denied for a variable nobody meant to set is the same
        wrong deny in a new costume."""
        self.commit({"hooks/a.sh": "#!/bin/sh\necho bye\n",
                     "notes/hardware/x.md": "how the rig is wired\n"}, "code plus a note")
        self.assert_allowed(self.push(DOC_GATE_NOTES="NEITHER"))
        self.assert_allowed(self.push(DOC_GATE_NOTES="", tool_use_id="tu2"))

    def test_a_script_under_root_notes_does_not_become_code_by_default(self):
        """THE SYMMETRY, and it is why the anchor MOVES rather than being deleted. Simply
        dropping `^notes?/` from NEITHER_RE would have let CODE_RE claim `notes/x.py`,
        making the gate STRICTER for exactly the repository that asked for the exclusion.
        Under the default the anchor is in DOC_RE instead, so everything under a root
        `notes/` satisfies the gate."""
        self.commit({"notes/2026-08-26-scratch.py": "x = 1\n"}, "a script under notes/")
        self.assert_allowed(self.push())
        # ...and under the knob it is NEITHER, which neither triggers nor satisfies.
        self.assert_allowed(self.push(DOC_GATE_NOTES="neither", tool_use_id="tu2"))

    def test_a_doc_under_a_nested_notes_directory_still_counts_as_documentation(self):
        """The `notes/` exclusion is about THIS repository's root-level dated log, and the
        header says so in as many words. Unanchored, `(^|/)notes?/` matched the segment at
        any depth, so `docs/notes/architecture.md` -- a real `.md` inside `docs/` -- was
        classified NEITHER and the push denied for carrying no documentation. That is the
        one outcome this gate must never produce, and the reason named the doc file
        nowhere, so nothing on any surface said why. Reproduced 2026-08-26 by a cold
        reviewer against a real repository and a real bare remote."""
        self.commit({"bin/tool.sh": "#!/bin/sh\ntrue\n",
                     "docs/notes/architecture.md": "# Architecture\n"},
                    "code plus a doc under docs/notes/")
        self.assert_allowed(self.push())

    def test_code_under_a_nested_notes_directory_is_still_code(self):
        """The same anchor, in the other direction and with the opposite consequence.
        `src/notes/parser.py` was excluded before it could be counted as CODE, so a push
        carrying only that file was silently allowed -- the permissive direction, which is
        why it would never have announced itself."""
        self.commit({"src/notes/parser.py": "def parse():\n    return 1\n"},
                    "code under a nested notes/ directory")
        reason = self.assert_denied(self.push())
        self.assertIn("src/notes/parser.py", reason)

    def test_a_root_level_note_beside_a_real_doc_still_leaves_the_doc_counted(self):
        """Non-vacuity for the anchor: the rule it protects must still fire at the root.

        `README.md` is written with content that DIFFERS from what setUp seeded. Written
        with the seeded bytes it is not a change, so it never reaches the diff the gate
        reads, and the test would have passed or failed for a reason unrelated to its
        name."""
        self.commit({"hooks/a.sh": "#!/bin/sh\necho bye\n",
                     "notes/2026-08-26-session.md": "log\n",
                     "README.md": "# project\n\na sentence setUp did not write\n"},
                    "code, a note, and a real doc")
        self.assert_allowed(self.push())

    def test_capitalised_documentation_directories_still_count_as_documentation(self):
        """`Documentation/` is git's own convention and the kernel's, and `Docs/` and
        `Doc/` are ordinary. All three were classified as neither, because `DOC_RE` was
        matched case-sensitively, and the push was denied for carrying no documentation
        while carrying one. Found by a cold reviewer on 2026-08-27 against a real
        repository and a real bare remote.

        Written through `git update-index --cacheinfo` so a case-insensitive filesystem
        cannot fold the path and make this pass for the wrong reason."""
        for d in ("Documentation", "Docs", "Doc", "Man"):
            with self.subTest(directory=d):
                self.setUp()
                self.commit_cacheinfo({"bin/tool.sh": "#!/bin/sh\ntrue\n",
                                       "%s/guide.txt" % d: "prose\n"},
                                      "code plus a doc under %s/" % d)
                self.assert_allowed(self.push())

    def test_capitalised_and_lowercased_bare_doc_names_still_count(self):
        """`Readme` and `readme` are as conventional as `README`."""
        for name in ("Readme.md", "readme.md", "Changelog", "changelog.rst"):
            with self.subTest(name=name):
                self.setUp()
                self.commit_cacheinfo({"bin/tool.sh": "#!/bin/sh\ntrue\n",
                                       name: "prose\n"}, "code plus %s" % name)
                self.assert_allowed(self.push())

    def test_an_uppercase_extension_still_counts_as_documentation(self):
        self.commit_cacheinfo({"bin/tool.sh": "#!/bin/sh\ntrue\n",
                               "guide.MD": "prose\n"}, "code plus an uppercase .MD")
        self.assert_allowed(self.push())

    def test_a_capitalised_notes_directory_counts_as_documentation(self):
        """THE ASYMMETRY IS DELIBERATE AND THIS TEST EXISTS TO STOP IT BEING TIDIED AWAY.

        `NEITHER_RE` was briefly given the same `-i` as the other two, to stop a
        capitalised directory sidestepping the exclusion. That REINTRODUCED, one commit
        later and under a different spelling, the defect the `^notes?/` anchor had just
        fixed: `Notes/design.md` beside a code file went from allowed to denied, with the
        reason naming no documentation file. A fourth cold reviewer caught it on
        2026-08-27 by driving the previous commit's hook and HEAD's side by side.

        The two directions are not symmetrical. A sidestepped exclusion costs a MISSED
        deny, which this gate tolerates by design; a case-folded one costs a WRONG deny of
        work that carries documentation, which it does not tolerate at all.

        Asserted under BOTH settings of `DOC_GATE_NOTES`: under the default the anchor is
        in DOC_RE, which does take the `-i`, so this is documentation directly; under
        `neither` it is documentation because NEITHER_RE does not fold the case."""
        self.commit_cacheinfo({"bin/tool.sh": "#!/bin/sh\ntrue\n",
                               "Notes/design.md": "prose\n"},
                              "code plus a doc under a capitalised Notes/")
        self.assert_allowed(self.push())
        self.assert_allowed(self.push(DOC_GATE_NOTES="neither", tool_use_id="tu2"))

    def test_the_lowercase_notes_exclusion_still_holds(self):
        """The partner, under `DOC_GATE_NOTES=neither` -- the setting the asymmetry above
        is about. Without it the test above is satisfied by a gate that stopped excluding
        notes altogether, which under that setting would let every push this repository
        makes go through: the difference between a gate and an ornament."""
        self.commit_cacheinfo({"hooks/a.sh": "#!/bin/sh\necho bye\n",
                               "notes/2026-08-26-session.md": "log\n"},
                              "code plus a lowercase note")
        reason = self.assert_denied(self.push(DOC_GATE_NOTES="neither"))
        self.assertIn("hooks/a.sh", reason)
        self.assertNotIn("notes/2026-08-26-session.md", reason)

    def test_the_user_supplied_code_exclude_stays_case_sensitive(self):
        """`DOC_GATE_CODE_EXCLUDE` is a regex the USER wrote, so the user decides its
        case. Nothing pinned this: mutating its `grep -qE` to `-qiE` left all 77 tests
        green while flipping a real decision, so a later "make the classifiers
        consistent" refactor would have sailed straight through."""
        self.commit_cacheinfo({"Tests/test_a.py": "def test_a():\n    pass\n"},
                              "code under a capitalised Tests/")
        reason = self.assert_denied(self.push(DOC_GATE_CODE_EXCLUDE="^tests?/"))
        self.assertIn("Tests/test_a.py", reason)

    def test_the_code_exclude_does_apply_in_the_case_the_user_wrote(self):
        """NON-VACUITY: the test above must fail because of the CASE, not because the
        knob is ignored outright."""
        self.commit_cacheinfo({"tests/test_a.py": "def test_a():\n    pass\n"},
                              "code under a lowercase tests/")
        self.assert_allowed(self.push(DOC_GATE_CODE_EXCLUDE="^tests?/"))

    def test_a_shell_script_with_no_extension_under_bin_counts_as_code(self):
        """It has to be caught by PATH, because a deleted file has no shebang left to
        read. This is how `bin/skillforge` is classified."""
        self.commit({"bin/skillthing": "#!/usr/bin/env bash\ntrue\n"}, "a new CLI")
        reason = self.assert_denied(self.push())
        self.assertIn("bin/skillthing", reason)

    # ================================================================= failing open
    def test_nothing_ahead_of_the_upstream_is_allowed(self):
        self.assert_allowed(self.push(), "no commits are about to leave")

    def test_a_repository_with_no_upstream_is_allowed(self):
        other = os.path.join(self.tmp, "noupstream")
        self.git("init", "-q", other, cwd=self.tmp)
        with open(os.path.join(other, "x.py"), "w", encoding="utf-8") as fh:
            fh.write("x = 1\n")
        self.git("add", "-A", cwd=other)
        self.git("commit", "-qm", "only commit", cwd=other)
        self.assert_allowed(self.push(cwd=other), "@{u} does not resolve")

    def test_a_directory_that_is_not_a_repository_is_allowed(self):
        plain = os.path.join(self.tmp, "plain")
        os.makedirs(plain)
        self.assert_allowed(self.push(cwd=plain), "not a git repository")

    def test_a_working_directory_that_does_not_exist_is_allowed(self):
        self.commit({"hooks/a.sh": "x\n"})
        self.assert_allowed(self.push(cwd=os.path.join(self.tmp, "gone")))

    def test_a_detached_head_is_allowed(self):
        self.commit({"hooks/a.sh": "#!/bin/sh\necho bye\n"})
        self.git("checkout", "-q", "--detach", "HEAD")
        self.assert_allowed(self.push(), "detached HEAD has no @{u}")

    def test_more_commits_than_the_cap_fails_open(self):
        """A first push of an existing history is not the defect this gate is for."""
        self.commit({"hooks/a.sh": "#!/bin/sh\n1\n"}, "one")
        self.commit({"hooks/b.sh": "#!/bin/sh\n2\n"}, "two")
        self.assert_allowed(self.push(DOC_GATE_MAX_COMMITS="1"), "2 commits, cap 1")
        # ...and the same tree under the default cap is refused, so the test above is
        # measuring the cap rather than something else.
        self.assertIn("hooks/a.sh", self.assert_denied(self.push(session="s2")))

    def test_a_non_numeric_cap_falls_back_to_the_default_instead_of_erroring(self):
        self.commit({"hooks/a.sh": "#!/bin/sh\necho bye\n"})
        r = self.push(DOC_GATE_MAX_COMMITS="lots")
        self.assertEqual(r.stderr, "")
        self.assert_denied(r)

    def test_a_non_bash_tool_is_ignored(self):
        self.commit({"hooks/a.sh": "#!/bin/sh\necho bye\n"})
        self.assert_allowed(self.run_hook(self.payload("git push", tool="Write")))

    def test_another_event_is_ignored(self):
        self.commit({"hooks/a.sh": "#!/bin/sh\necho bye\n"})
        self.assert_allowed(self.run_hook(self.payload("git push", event="PostToolUse")))

    def test_the_off_switch_silences_the_gate(self):
        self.commit({"hooks/a.sh": "#!/bin/sh\necho bye\n"})
        self.assert_allowed(self.push(SKILL_COMPOUNDER_DOC_GATE="0"))

    # ============================================================ recognising a push
    # Every spelling below is a REAL shape a push takes. Each runs in its own session so
    # the once-per-HEAD rule cannot silence a later one and make this test vacuous.
    def test_every_push_spelling_is_recognised(self):
        self.commit({"hooks/a.sh": "#!/bin/sh\necho bye\n"})
        parent = os.path.dirname(self.repo)
        spellings = [
            ("git push", None),
            ("git push --force-with-lease origin HEAD", None),
            ("git push -u origin main", None),
            # a leading environment assignment, bare and quoted
            ("GIT_TRACE=1 git push", None),
            ('GIT_SSH_COMMAND="ssh -i /tmp/k" git push origin HEAD', None),
            # git's own options, including the one that takes a separate argument
            ("git -c push.default=simple push", None),
            ("git --no-pager push", None),
            # inside a chain
            ("./run_tests.sh && git push", None),
            ("make check; git push origin main", None),
            ("git add -A && git commit -m wip && git push", None),
            # multiline, which is how this repo writes long commands
            ("./run_tests.sh\ngit push origin HEAD\n", None),
            # a `cd` decides which repository the push is about
            ("cd %s && git push" % os.path.basename(self.repo), parent),
            # and `git -C` beats it
            ("git -C %s push" % self.repo, parent),
        ]
        for i, (cmd, cwd) in enumerate(spellings):
            with self.subTest(command=cmd):
                r = self.push(cmd, session="spell%d" % i, cwd=cwd)
                reason = self.assert_denied(r)
                self.assertIn("hooks/a.sh", reason)

    def test_text_that_merely_mentions_a_push_is_not_one(self):
        """The command-position matcher from claim-gate.sh, reused. A plain substring
        match on `git push` refuses a grep, a note and a README."""
        self.commit({"hooks/a.sh": "#!/bin/sh\necho bye\n"})
        lookalikes = [
            'echo "git push"',
            'grep -rn "git push" .',
            "# git push",
            'git commit -m "ready to push"',
            "git log --oneline | head -20",
            "git status",
            "gh pr create --title 'git push notes'",
            "git pushd",
            "cat README.md | grep push",
        ]
        for i, cmd in enumerate(lookalikes):
            with self.subTest(command=cmd):
                self.assert_allowed(self.push(cmd, session="look%d" % i),
                                    "not a push: %r" % cmd)

    def test_a_heredoc_that_only_contains_the_words_is_not_a_push(self):
        """claim-gate.sh's first heredoc handling pounced on the first `<<` and read the
        rest of the command as content, denying real work. Same awk, same fix."""
        self.commit({"hooks/a.sh": "#!/bin/sh\necho bye\n"})
        cmd = (
            "cat > /tmp/plan.md <<'EOF'\n"
            "Step 3: git push origin main\n"
            "EOF\n"
            "echo written\n"
        )
        self.assert_allowed(self.push(cmd, session="hd1"), "the push is document text")

    def test_a_real_push_after_a_heredoc_is_still_recognised(self):
        """The complement, so the test above is not passing by refusing to look."""
        self.commit({"hooks/a.sh": "#!/bin/sh\necho bye\n"})
        cmd = (
            "cat > /tmp/plan.md <<'EOF'\n"
            "some notes\n"
            "EOF\n"
            "git push origin HEAD\n"
        )
        self.assertIn("hooks/a.sh", self.assert_denied(self.push(cmd, session="hd2")))

    def test_a_dry_run_push_is_not_a_push(self):
        """It writes to no remote, so there is nothing to gate, and refusing it would
        refuse the safest way to look at what a push would do."""
        self.commit({"hooks/a.sh": "#!/bin/sh\necho bye\n"})
        for i, cmd in enumerate(["git push --dry-run",
                                 "git push -n origin HEAD",
                                 "git push origin main --dry-run"]):
            with self.subTest(command=cmd):
                self.assert_allowed(self.push(cmd, session="dry%d" % i))

    # ============================================== once per session, per HEAD sha
    def test_the_gate_refuses_a_given_head_only_once_per_session(self):
        self.commit({"hooks/a.sh": "#!/bin/sh\necho bye\n"})
        self.assert_denied(self.push(tool_use_id="tu1"))
        self.assert_allowed(self.push(tool_use_id="tu2"),
                            "the same HEAD, already refused once in this session")

    def test_a_different_session_is_judged_afresh(self):
        self.commit({"hooks/a.sh": "#!/bin/sh\necho bye\n"})
        self.assert_denied(self.push(session="s1"))
        self.assert_denied(self.push(session="s2"))

    def test_a_moved_head_is_re_evaluated_from_scratch(self):
        """The expected response to the deny is a NEW commit carrying documentation, so
        the marker has to move with HEAD or the fix could never be checked."""
        self.commit({"hooks/a.sh": "#!/bin/sh\necho bye\n"})
        self.assert_denied(self.push(tool_use_id="tu1"))
        self.commit({"README.md": "# project\n\ndocuments the change\n"}, "docs")
        self.assert_allowed(self.push(tool_use_id="tu2"),
                            "HEAD moved and now carries a doc change")

    def test_a_moved_head_that_is_still_code_only_is_refused_again(self):
        self.commit({"hooks/a.sh": "#!/bin/sh\necho bye\n"})
        self.assert_denied(self.push(tool_use_id="tu1"))
        self.commit({"hooks/b.sh": "#!/bin/sh\nmore\n"}, "more code")
        reason = self.assert_denied(self.push(tool_use_id="tu2"))
        self.assertIn("2 commits are about to leave", reason)
        self.assertIn("hooks/b.sh", reason)

    def test_double_delivery_denies_once(self):
        """Both wirings active deliver the identical event twice (measured on 2.1.241)."""
        self.commit({"hooks/a.sh": "#!/bin/sh\necho bye\n"})
        first = self.push(tool_use_id="tu-same")
        second = self.push(tool_use_id="tu-same")
        outs = [r for r in (first, second) if r.stdout.strip()]
        self.assertEqual(len(outs), 1,
                         "exactly one of two deliveries may deny; got %r"
                         % [r.stdout for r in (first, second)])

    # ============================================================= the escape hatch
    def test_the_trailer_override_lets_the_push_through_and_is_recorded(self):
        self.commit({"hooks/a.sh": "#!/bin/sh\necho bye\n"},
                    "tighten a guard\n\nDoc-Gate-Override: no user-visible behaviour changed")
        head = self.git("rev-parse", "HEAD").strip()
        self.assert_allowed(self.push())
        rows = self.overrides()
        self.assertEqual(len(rows), 1, rows)
        row = rows[0]
        self.assertEqual(row["kind"], "trailer")
        self.assertEqual(row["reason"], "no user-visible behaviour changed")
        self.assertEqual(row["head"], head)
        self.assertEqual(row["session"], "s1")
        self.assertEqual(row["ts"], int(NOW))
        self.assertEqual(row["commits"], 1)
        self.assertEqual(row["code_files"], 1)
        self.assertEqual(row["files"], ["hooks/a.sh"])

    def test_the_inline_override_lets_the_push_through_and_is_recorded(self):
        self.commit({"hooks/a.sh": "#!/bin/sh\necho bye\n"})
        r = self.push('DOC_GATE_OVERRIDE="whitespace only" git push origin HEAD')
        self.assert_allowed(r)
        rows = self.overrides()
        self.assertEqual(len(rows), 1, rows)
        self.assertEqual(rows[0]["kind"], "inline")
        self.assertEqual(rows[0]["reason"], "whitespace only")

    def test_an_override_with_no_reason_is_not_an_override(self):
        """Both forms cost a written reason. An empty one is not a deliberate act."""
        self.commit({"hooks/a.sh": "#!/bin/sh\necho bye\n"},
                    "tighten a guard\n\nDoc-Gate-Override:")
        self.assert_denied(self.push())
        self.assertEqual(self.overrides(), [])

    def test_the_override_is_not_read_from_the_environment(self):
        """An exported DOC_GATE_OVERRIDE would silence the gate forever with nothing on
        any surface to say why -- an escape taken without noticing it was taken. Only
        the command text counts."""
        self.commit({"hooks/a.sh": "#!/bin/sh\necho bye\n"})
        self.assert_denied(self.push(DOC_GATE_OVERRIDE="set in the shell profile"))
        self.assertEqual(self.overrides(), [])

    def test_double_delivery_writes_one_override_row_not_two(self):
        self.commit({"hooks/a.sh": "#!/bin/sh\necho bye\n"})
        cmd = "DOC_GATE_OVERRIDE='vendored dependency bump' git push"
        self.assert_allowed(self.push(cmd, tool_use_id="tu-dup"))
        self.assert_allowed(self.push(cmd, tool_use_id="tu-dup"))
        self.assertEqual(len(self.overrides()), 1, self.overrides())

    def test_two_genuinely_separate_overrides_are_both_counted(self):
        """The complement of the test above: idempotence must not collapse real events."""
        self.commit({"hooks/a.sh": "#!/bin/sh\necho bye\n"})
        cmd = "DOC_GATE_OVERRIDE='first' git push"
        self.assert_allowed(self.push(cmd, tool_use_id="tu-a"))
        self.assert_allowed(self.push("DOC_GATE_OVERRIDE='second' git push",
                                      tool_use_id="tu-b"))
        self.assertEqual([r["reason"] for r in self.overrides()], ["first", "second"])

    def test_an_override_reason_with_awkward_characters_stays_parseable(self):
        """The row is built by `jq -n`, so a quote or a backslash cannot produce a line
        no reader can parse."""
        self.commit({"hooks/a.sh": "#!/bin/sh\necho bye\n"},
                    'refactor\n\nDoc-Gate-Override: says "no docs" \\ needed, {json}')
        self.assert_allowed(self.push())
        self.assertEqual(self.overrides()[0]["reason"],
                         'says "no docs" \\ needed, {json}')

    def test_no_override_row_is_written_for_a_push_that_was_allowed_anyway(self):
        """Only real escapes are counted, or the count means nothing."""
        self.commit({"README.md": "# project\n\nprose\n"},
                    "docs\n\nDoc-Gate-Override: not needed here")
        self.assert_allowed(self.push())
        self.assertEqual(self.overrides(), [])

    # ==================================================================== the knobs
    def test_the_code_exclude_knob_makes_a_path_neither(self):
        self.commit({"tests/test_x.py": "def test_x():\n    assert True\n"}, "a test")
        self.assert_denied(self.push(session="s1"))   # a test is code by default
        self.assert_allowed(self.push(session="s2", DOC_GATE_CODE_EXCLUDE="^tests?/"))

    def test_the_deny_names_at_most_max_named_files(self):
        self.commit({"hooks/a.sh": "1\n", "hooks/b.sh": "2\n", "hooks/c.sh": "3\n"},
                    "three files")
        reason = self.assert_denied(self.push(DOC_GATE_MAX_NAMED="2"))
        self.assertIn("... and 1 more.", reason)
        self.assertEqual(len(re.findall(r"^    - ", reason, re.M)), 2, reason)

    def test_the_debug_dump_captures_the_raw_payload(self):
        dump = os.path.join(self.tmp, "dump.jsonl")
        self.commit({"hooks/a.sh": "#!/bin/sh\necho bye\n"})
        self.assert_denied(self.push(DOC_GATE_DEBUG_DUMP=dump))
        with open(dump, encoding="utf-8") as fh:
            self.assertEqual(json.loads(fh.read())["tool_name"], "Bash")

    # ========================================== the refspec: what the push actually sends
    # The gate judges `@{u}..HEAD`. Until 2026-08-26 it did that no matter what the push
    # SENT, so a tag push, `--tags` and a branch deletion were each denied with a reason
    # stating a falsehood about them -- and it was the deny with no cheap way out, since
    # the trailer override means amending a commit unrelated to the refused operation.
    # Each test below is paired with its complement so neither direction can pass by the
    # gate having simply stopped looking.

    def sanity_denies_a_plain_push(self, session):
        """The control every refspec test needs: the SAME tree, pushed plainly, is still
        refused. Without it a test that asserts `allowed` would pass just as well against
        a gate that had been switched off."""
        self.assertIn("hooks/a.sh", self.assert_denied(self.push(session=session)))

    def test_a_tag_push_carries_no_commit_and_is_not_this_gates_business(self):
        self.commit({"hooks/a.sh": "#!/bin/sh\necho bye\n"}, "code only")
        self.git("tag", "v1.0.0")
        self.assert_allowed(self.push("git push origin v1.0.0", session="tag1"),
                            "a tag push sends no commit of this branch")
        self.sanity_denies_a_plain_push("tag2")

    def test_pushing_only_tags_is_allowed(self):
        self.commit({"hooks/a.sh": "#!/bin/sh\necho bye\n"}, "code only")
        self.git("tag", "v1.0.0")
        for i, cmd in enumerate(["git push --tags", "git push --tags origin"]):
            with self.subTest(command=cmd):
                self.assert_allowed(self.push(cmd, session="tags%d" % i))
        self.sanity_denies_a_plain_push("tags9")

    def test_a_branch_deletion_is_allowed_in_both_spellings(self):
        self.git("branch", "somebranch")
        self.git("push", "-q", "origin", "somebranch")
        self.commit({"hooks/a.sh": "#!/bin/sh\necho bye\n"}, "code only")
        for i, cmd in enumerate(["git push --delete origin somebranch",
                                 "git push -d origin somebranch",
                                 "git push origin :somebranch"]):
            with self.subTest(command=cmd):
                self.assert_allowed(self.push(cmd, session="del%d" % i),
                                    "a deletion sends no commit")
        self.sanity_denies_a_plain_push("del9")

    def test_pushing_a_different_branch_is_not_judged_by_this_branchs_commits(self):
        """`@{u}..HEAD` describes the current branch and nothing else, so a push of some
        other branch is judged by evidence that does not describe it. Fail open."""
        self.git("branch", "otherbranch")
        self.commit({"hooks/a.sh": "#!/bin/sh\necho bye\n"}, "code only")
        self.assert_allowed(self.push("git push origin otherbranch", session="ob1"))
        self.sanity_denies_a_plain_push("ob2")

    def test_the_refspecs_that_do_send_this_branch_are_still_judged(self):
        """The complement of every test above: reading the refspec must not have gutted
        the gate. Each of these really does carry the current branch's commits."""
        self.commit({"hooks/a.sh": "#!/bin/sh\necho bye\n"}, "code only")
        judged = [
            "git push",
            "git push origin",
            "git push origin HEAD",
            "git push origin main",
            "git push origin HEAD:refs/heads/main",
            "git push origin refs/heads/main:refs/heads/main",
            "git push --force-with-lease origin +main:main",
            "git push --all origin",
            "git push --mirror origin",
            # `--tags` ALONGSIDE a branch refspec: the branch is still being sent.
            "git push --tags origin main",
            # an option that eats the following word, so `origin` is the remote and there
            # is no refspec at all -- a default push of the current branch.
            "git push -o ci.skip origin",
            "git push --repo origin",
        ]
        for i, cmd in enumerate(judged):
            with self.subTest(command=cmd):
                reason = self.assert_denied(self.push(cmd, session="judge%d" % i))
                self.assertIn("hooks/a.sh", reason)

    def test_follow_tags_is_not_tags_and_still_sends_the_branch(self):
        """`--follow-tags` was lumped in with `--tags`, and they are opposites for this
        gate's purpose: `--tags` pushes refs/tags/* INSTEAD of the branch, while
        `--follow-tags` pushes the branch AND its reachable annotated tags. So a
        code-only push spelled `git push --follow-tags` went through with no override
        recorded -- exactly the push this gate exists to refuse (reproduced 2026-08-26).

        The distinction is MEASURED here, not asserted from the git manual, because the
        whole rule rests on it."""
        self.commit({"hooks/a.sh": "#!/bin/sh\necho bye\n"}, "code only")
        # Annotated: `--follow-tags` follows annotated tags only, so a lightweight tag
        # would make the precondition below pass for the wrong reason.
        self.git("tag", "-a", "v1.0.0", "-m", "annotated")

        tags_only = self.dry_run("--tags", "origin")
        follow = self.dry_run("--follow-tags", "origin")
        self.assertNotIn("main -> main", tags_only,
                         "`--tags` alone must not send the branch; git said %r"
                         % tags_only)
        self.assertIn("main -> main", follow,
                      "`--follow-tags` must send the branch; git said %r" % follow)
        self.assertIn("v1.0.0", follow, "`--follow-tags` must also send the tag")

        for i, cmd in enumerate(["git push --follow-tags",
                                 "git push --follow-tags origin",
                                 "git push --follow-tags -o ci.skip origin"]):
            with self.subTest(command=cmd):
                self.assertIn("hooks/a.sh",
                              self.assert_denied(self.push(cmd, session="ft%d" % i)))

    def test_tags_alongside_follow_tags_still_sends_only_tags(self):
        """The discriminator for the fix above: it must separate the two options, not
        delete the `--tags` handling. Measured on git 2.50.1 -- with BOTH flags, in
        either order, git sends the tag and NOT the branch, so `--tags` still wins and
        the gate must still pass the push."""
        self.commit({"hooks/a.sh": "#!/bin/sh\necho bye\n"}, "code only")
        self.git("tag", "-a", "v1.0.0", "-m", "annotated")
        for args in (("--tags", "--follow-tags", "origin"),
                     ("--follow-tags", "--tags", "origin")):
            out = self.dry_run(*args)
            self.assertNotIn("main -> main", out,
                             "git push %s sent the branch: %r" % (" ".join(args), out))
        for i, cmd in enumerate(["git push --tags --follow-tags origin",
                                 "git push --follow-tags --tags origin"]):
            with self.subTest(command=cmd):
                self.assert_allowed(self.push(cmd, session="ftt%d" % i),
                                    "`--tags` wins over `--follow-tags`")
        self.sanity_denies_a_plain_push("ftt9")

    def test_a_bare_at_is_the_documented_synonym_for_head(self):
        """`@` alone is git's documented shorthand for `HEAD` (gitrevisions: "@ alone is
        a shortcut for HEAD"). The source-matching test knew only `HEAD`, the branch name
        and `refs/heads/<branch>`, so `git push origin @` escaped the gate."""
        self.commit({"hooks/a.sh": "#!/bin/sh\necho bye\n"}, "code only")
        # Measured, not assumed: this git really does resolve `@` to HEAD.
        self.assertEqual(self.git("rev-parse", "@").strip(),
                         self.git("rev-parse", "HEAD").strip())
        for i, cmd in enumerate(["git push origin @",
                                 "git push origin @:refs/heads/main",
                                 "git push origin +@:main"]):
            with self.subTest(command=cmd):
                self.assertIn("hooks/a.sh",
                              self.assert_denied(self.push(cmd, session="at%d" % i)))

    def test_a_ref_whose_name_merely_begins_with_at_is_not_head(self):
        """The complement: `@` must be matched EXACTLY, not as a prefix. A branch
        literally named `@foo` is a different ref, and judging it by `@{u}..HEAD` would
        be the tag-push falsehood all over again."""
        self.git("branch", "@foo")
        self.git("push", "-q", "origin", "@foo")
        self.commit({"hooks/a.sh": "#!/bin/sh\necho bye\n"}, "code only")
        self.assert_allowed(self.push("git push origin @foo", session="atf1"),
                            "`@foo` is a ref of its own, not HEAD")
        self.sanity_denies_a_plain_push("atf2")

    def test_pushing_only_submodules_leaves_the_superproject_unpushed(self):
        """`--recurse-submodules=only` pushes the submodules and leaves the superproject
        UNPUSHED, so no commit of this branch leaves and there is nothing here to judge.
        The gate denied it, which is the wrong direction: a refusal of a push that was
        never going to carry the code it names."""
        self.commit({"hooks/a.sh": "#!/bin/sh\necho bye\n"}, "code only")
        out = self.dry_run("--recurse-submodules=only", "origin")
        self.assertNotIn("main -> main", out,
                         "`--recurse-submodules=only` sent the branch: %r" % out)
        for i, cmd in enumerate(["git push --recurse-submodules=only",
                                 "git push --recurse-submodules=only origin",
                                 "git push --recurse-submodules=only origin main"]):
            with self.subTest(command=cmd):
                self.assert_allowed(self.push(cmd, session="rso%d" % i),
                                    "the superproject is left unpushed")
        # The other spellings DO push the superproject and must still be judged.
        for i, cmd in enumerate(["git push --recurse-submodules=check origin",
                                 "git push --recurse-submodules=on-demand origin",
                                 "git push --recurse-submodules=no origin"]):
            with self.subTest(command=cmd):
                self.assertIn("hooks/a.sh",
                              self.assert_denied(self.push(cmd, session="rsx%d" % i)))

    def test_recurse_submodules_takes_its_value_as_a_separate_word_too(self):
        """`--recurse-submodules` is the one push option that both CONSUMES the following
        word and needs that word READ. Stepping over it the way the other five consumed
        words are stepped over would lose `only`; not consuming it at all would shift the
        positional count and read the REMOTE as a refspec.

        That git eats the separate word is measured here, because the tokeniser's whole
        arithmetic depends on it and the manual only documents the `=` spelling."""
        self.commit({"hooks/a.sh": "#!/bin/sh\necho bye\n"}, "code only")
        # If the following word were NOT consumed, `only` would be the remote and git
        # would call it a bad repository rather than a bad option value.
        r = subprocess.run(
            ["git", "push", "--recurse-submodules", "__SENT__", "--dry-run"],
            cwd=self.repo, env=self.gitenv, capture_output=True, text=True,
            stdin=subprocess.DEVNULL, timeout=120,
        )
        self.assertIn("bad recurse-submodules argument: __SENT__", r.stdout + r.stderr,
                      "git did not consume the following word: %r" % (r.stdout + r.stderr))
        self.assertNotIn("main -> main", self.dry_run("--recurse-submodules", "only",
                                                      "origin"))

        self.assert_allowed(self.push("git push --recurse-submodules only origin",
                                      session="rsw1"),
                            "the superproject is left unpushed")
        # `check` is consumed the same way and DOES send the branch: the value is read,
        # not just skipped. And `origin` must still be counted as the REMOTE, not as a
        # refspec -- if the word were not consumed, `only`/`check` would take that slot
        # and `origin` would be read as a refspec that names no branch of ours, which
        # would pass for entirely the wrong reason.
        self.assertIn("hooks/a.sh",
                      self.assert_denied(self.push(
                          "git push --recurse-submodules check origin", session="rsw2")))

    # =========================================== last-wins option resolution (git's own)
    # THE PARSER RESOLVES LAST-WINS BECAUSE GIT DOES, and every row of that claim is
    # MEASURED here rather than restated from the manual. See the LAST-WINS block in the
    # header of hooks/doc-gate.sh for the table these four tests establish.

    def test_recurse_submodules_resolves_last_wins_the_way_git_does(self):
        """`f_nosuper` was a ONE-WAY LATCH: the first `only` anywhere in the command
        decided the verdict and no later spelling could clear it. git resolves
        `--recurse-submodules` LAST-WINS, so
        `git push --recurse-submodules=only --recurse-submodules=on-demand` really does
        send the superproject -- and the gate allowed it. A gate failing open on exactly
        the push it exists to judge, introduced by the fix for the `=only` row itself."""
        self.commit({"hooks/a.sh": "#!/bin/sh\necho bye\n"}, "code only")

        # (1) MEASURE git: which spelling comes LAST is what decides.
        sends_super = [
            ("--recurse-submodules=only", "--recurse-submodules=on-demand", "origin"),
            ("--recurse-submodules", "only", "--recurse-submodules", "on-demand",
             "origin"),
            ("--recurse-submodules=only", "--recurse-submodules", "no", "origin"),
            ("--recurse-submodules=only", "--no-recurse-submodules", "origin"),
        ]
        keeps_super_put = [
            ("--recurse-submodules=on-demand", "--recurse-submodules=only", "origin"),
            ("--recurse-submodules", "on-demand", "--recurse-submodules", "only",
             "origin"),
            ("--recurse-submodules", "on-demand", "--recurse-submodules=only", "origin"),
            ("--no-recurse-submodules", "--recurse-submodules=only", "origin"),
        ]
        for args in sends_super:
            self.assertIn("main -> main", self.dry_run(*args),
                          "git push %s did NOT send the branch" % " ".join(args))
        for args in keeps_super_put:
            self.assertNotIn("main -> main", self.dry_run(*args),
                             "git push %s DID send the branch" % " ".join(args))

        # (2) The gate must agree with what git just said, in both directions.
        for i, args in enumerate(sends_super):
            cmd = "git push " + " ".join(args)
            with self.subTest(judged=cmd):
                self.assertIn("hooks/a.sh",
                              self.assert_denied(self.push(cmd, session="lwrs%d" % i)))
        for i, args in enumerate(keeps_super_put):
            cmd = "git push " + " ".join(args)
            with self.subTest(passed=cmd):
                self.assert_allowed(self.push(cmd, session="lwrsp%d" % i),
                                    "the last spelling leaves the superproject unpushed")

    def test_tags_resolves_last_wins_the_way_git_does(self):
        """The identical latch in `f_tags`, and the same wrong direction: once `--tags`
        was seen, `--no-tags` could not clear it, so a code-only push spelled
        `git push --tags --no-tags` was allowed while git sent the branch."""
        self.commit({"hooks/a.sh": "#!/bin/sh\necho bye\n"}, "code only")
        self.git("tag", "-a", "v1.0.0", "-m", "annotated")

        sends_branch = self.dry_run("--tags", "--no-tags", "origin")
        tags_only = self.dry_run("--no-tags", "--tags", "origin")
        self.assertIn("main -> main", sends_branch,
                      "`--tags --no-tags` must send the branch; git said %r"
                      % sends_branch)
        self.assertNotIn("main -> main", tags_only,
                         "`--no-tags --tags` must not send the branch; git said %r"
                         % tags_only)
        self.assertIn("v1.0.0", tags_only)

        self.assertIn("hooks/a.sh",
                      self.assert_denied(self.push("git push --tags --no-tags origin",
                                                   session="lwt1")))
        self.assert_allowed(self.push("git push --no-tags --tags origin",
                                      session="lwt2"),
                            "`--tags` last means refs/tags/* only")

    def test_delete_resolves_last_wins_the_way_git_does(self):
        """`f_delete` is the third latch of the same shape. `--delete --no-delete origin
        main` is an ordinary push of `main`, which git proves by reporting `main -> main`
        where the deletion spelling reports `[deleted]`."""
        self.commit({"hooks/a.sh": "#!/bin/sh\necho bye\n"}, "code only")

        undeleted = self.dry_run("--delete", "--no-delete", "origin", "main")
        deleted = self.dry_run("--no-delete", "--delete", "origin", "main")
        self.assertIn("main -> main", undeleted,
                      "`--delete --no-delete` must push, not delete; git said %r"
                      % undeleted)
        self.assertIn("[deleted]", deleted,
                      "`--no-delete --delete` must delete; git said %r" % deleted)

        self.assertIn("hooks/a.sh",
                      self.assert_denied(self.push(
                          "git push --delete --no-delete origin main", session="lwd1")))
        self.assert_allowed(self.push("git push --no-delete --delete origin main",
                                      session="lwd2"),
                            "a deletion sends no commit")

    def test_all_and_mirror_are_independent_last_wins_flags(self):
        """`--all`/`--branches` and `--mirror` share ONE flag inside this gate, and git
        says they are two variables: `--no-all` clears `--all` and leaves `--mirror`
        alone. Collapsing them into a single last-wins flag would be a new bug of the
        same family, so the separation is measured before it is relied on."""
        self.commit({"hooks/a.sh": "#!/bin/sh\necho bye\n"}, "code only")
        self.git("tag", "-a", "v1.0.0", "-m", "annotated")

        # `--no-all` really does clear `--all`: with it, `--tags` is left alone and git
        # sends the tag and NOT the branch. (Without it the two options are a fatal
        # combination, which is itself proof `--all` was still set -- see below.)
        cleared = self.dry_run("--tags", "--all", "--no-all", "origin")
        self.assertNotIn("main -> main", cleared,
                         "`--all --no-all` still sent branches; git said %r" % cleared)
        self.assertIn("v1.0.0", cleared)
        rc, out = self.dry_run_raw("--tags", "--no-all", "--all", "origin")
        self.assertNotEqual(rc, 0)
        self.assertIn("cannot be used together", out,
                      "`--no-all --all` did not leave `--all` set; git said %r" % out)

        # `--no-all` does NOT clear `--mirror`: git still refuses to combine the mirror
        # with a refspec, which it could only do with `--mirror` still set.
        rc, out = self.dry_run_raw("--mirror", "--no-all", "origin", "v1.0.0")
        self.assertNotEqual(rc, 0)
        self.assertIn("--mirror can't be combined with refspecs", out,
                      "`--no-all` cleared `--mirror`; git said %r" % out)

        # The gate must agree: `--tags --all --no-all` sends no commit of this branch.
        self.assert_allowed(self.push("git push --tags --all --no-all origin",
                                      session="lwa1"),
                            "`--no-all` cleared `--all`, leaving refs/tags/* only")
        # And `--mirror` survives `--no-all`, so that push is still judged.
        self.assertIn("hooks/a.sh",
                      self.assert_denied(self.push(
                          "git push --tags --mirror --no-all origin", session="lwa2")))

    def test_a_quoted_option_value_is_still_read(self):
        """The tokeniser is `set -- $push_seg` over the RAW command text, so a consumed
        word arrives still wearing its quotes and `--recurse-submodules "only"` was not
        recognised as `only`. That is the REFUSING direction: a push that was never going
        to carry the superproject was denied for the code it names."""
        self.commit({"hooks/a.sh": "#!/bin/sh\necho bye\n"}, "code only")
        # git sees the shell-stripped word, and leaves the superproject unpushed.
        self.assertNotIn("main -> main",
                         self.dry_run("--recurse-submodules", "only", "origin"))
        for i, cmd in enumerate([
                'git push --recurse-submodules "only" origin',
                "git push --recurse-submodules 'only' origin",
                'git push --recurse-submodules="only" origin',
                "git push --recurse-submodules='only' origin"]):
            with self.subTest(command=cmd):
                self.assert_allowed(self.push(cmd, session="q%d" % i),
                                    "a quoted `only` is still `only`")

    def test_a_quoted_refspec_still_names_this_branch(self):
        """The same stripping, in the other direction: a quoted refspec must not escape
        the gate by wearing quotes the shell would have removed."""
        self.commit({"hooks/a.sh": "#!/bin/sh\necho bye\n"}, "code only")
        self.assertIn("main -> main", self.dry_run("origin", "main"))
        for i, cmd in enumerate(['git push origin "main"',
                                 "git push origin 'main'",
                                 'git push origin "+main:main"',
                                 'git push origin "HEAD"']):
            with self.subTest(command=cmd):
                self.assertIn("hooks/a.sh",
                              self.assert_denied(self.push(cmd, session="qr%d" % i)))

    # ================================================ non-ASCII paths in the file list
    def test_a_documentation_path_with_a_non_ascii_byte_is_still_documentation(self):
        """`git diff --name-only` C-QUOTES any path holding a non-ASCII byte, surrounding
        double quotes included, and those quotes defeat both of DOC_RE's anchors. A REAL
        documentation file was therefore classified NEITHER and the push denied for
        carrying no documentation -- the one outcome this gate must never produce."""
        self.commit({"hooks/a.sh": "#!/bin/sh\necho bye\n",
                     "docs/café.md": "accented prose\n"}, "code plus an accented doc")
        # The precondition, asserted rather than assumed: without the quoting there is no
        # defect here at all and this test would be measuring nothing.
        quoted = self.git("diff", "--name-only", "HEAD~1", "HEAD")
        self.assertIn('"', quoted,
                      "git no longer C-quotes this path, so the test is vacuous: %r"
                      % quoted)
        self.assert_allowed(self.push(session="nb1"),
                            "docs/café.md is documentation")

    def test_a_code_path_with_a_non_ascii_byte_is_still_code_and_is_named(self):
        """The complement: the fix must not have made every awkward path invisible."""
        self.commit({"hooks/café.sh": "#!/bin/sh\ntrue\n"}, "an accented script")
        reason = self.assert_denied(self.push(session="nb2"))
        self.assertIn("hooks/café.sh", reason)
        self.assertNotIn("\\303", reason)

    # ========================================= a git option must not swallow a subcommand
    def test_a_git_option_does_not_swallow_a_subcommand(self):
        """Every git option used to be allowed an optional separate argument, so
        `git <option> <subcommand> push` matched the push matcher: `git --no-pager stash
        push` was DENIED. Only the seven options that really take one may take one."""
        self.commit({"hooks/a.sh": "#!/bin/sh\necho bye\n"})
        not_pushes = [
            "git --no-pager stash push",
            "git --no-pager checkout push",
            "git --no-pager branch push",
            "git --literal-pathspecs stash push",
            # the controls the reviewer ran, which correctly did not match even before:
            "git stash push",
            "git -C %s stash push" % self.repo,
        ]
        for i, cmd in enumerate(not_pushes):
            with self.subTest(command=cmd):
                self.assert_allowed(self.push(cmd, session="nosub%d" % i),
                                    "not a push: %r" % cmd)
        # And the complement, so the matcher has not simply been narrowed into uselessness:
        # both the option that takes no argument and the one that does still reach `push`.
        for i, cmd in enumerate(["git --no-pager push",
                                 "git --literal-pathspecs push",
                                 "git -C %s push" % self.repo,
                                 "git -c push.default=simple push",
                                 "git --git-dir %s/.git push" % self.repo]):
            with self.subTest(command=cmd):
                self.assertIn("hooks/a.sh",
                              self.assert_denied(self.push(cmd, session="issub%d" % i)))

    # ============================== the override claim outlives a store it could not write
    def test_a_failed_override_append_does_not_burn_the_event(self):
        """A claim is taken only once the action is really going to happen. With
        `overrides.jsonl` present as a DIRECTORY the hook exited 0, wrote no row and left
        the claim behind, so repairing the store and re-delivering the identical event
        wrote NO row, ever -- the exact anti-pattern .claude/CLAUDE.md names."""
        self.commit({"hooks/a.sh": "#!/bin/sh\necho bye\n"})
        broken = os.path.join(self.state, "doc-gate", "overrides.jsonl")
        os.makedirs(broken)
        cmd = 'DOC_GATE_OVERRIDE="vendored bump" git push'
        r = self.push(cmd, tool_use_id="tu-burn")
        self.assert_allowed(r, "the push still proceeds; the gate never breaks a turn")
        self.assertEqual(r.stderr, "",
                         "a malformed override store must not leak to stderr")
        claims = os.path.join(self.state, "doc-gate", "claims")
        self.assertEqual(sorted(os.listdir(claims)) if os.path.isdir(claims) else [], [],
                         "the claim was burnt on an append that never happened")
        # Repair the store and re-deliver the IDENTICAL event.
        os.rmdir(broken)
        self.assert_allowed(self.push(cmd, tool_use_id="tu-burn"))
        self.assertEqual([r_["reason"] for r_ in self.overrides()], ["vendored bump"])
        # ...and it is still idempotent: a third delivery of that same event adds nothing.
        self.assert_allowed(self.push(cmd, tool_use_id="tu-burn"))
        self.assertEqual(len(self.overrides()), 1, self.overrides())

    def test_an_unwritable_debug_dump_leaks_nothing_to_stderr(self):
        """`2>/dev/null` must precede every `>` and `>>` in this file: bash applies
        redirections left to right, so with the order reversed the failure is reported on
        the shell's own stderr before the suppression exists."""
        self.commit({"hooks/a.sh": "#!/bin/sh\necho bye\n"})
        dump = os.path.join(self.tmp, "dumpdir")
        os.makedirs(dump)
        r = self.push(DOC_GATE_DEBUG_DUMP=dump)
        self.assertEqual(r.stderr, "")
        self.assert_denied(r)

    def test_no_redirection_in_the_script_suppresses_stderr_too_late(self):
        """The whole file, not only the line that was reported."""
        offenders = []
        for i, line in enumerate(hook_text().splitlines(), 1):
            code = line.split("#", 1)[0] if not line.lstrip().startswith("#") else ""
            if re.search(r"(?<![0-9<>])>>?[^>&]*\s2>/dev/null", code):
                offenders.append((i, line.strip()))
        self.assertEqual(offenders, [])

    # ==================================================== a deny always names a file
    def test_a_max_named_of_zero_still_names_one_file(self):
        """`head -n 0` prints nothing, so the reason read '...among them:', a blank line,
        and '... and 1 more.' -- a refusal naming no file at all."""
        self.commit({"hooks/a.sh": "#!/bin/sh\necho bye\n"})
        reason = self.assert_denied(self.push(DOC_GATE_MAX_NAMED="0"))
        self.assertEqual(re.findall(r"^    - (.+)$", reason, re.M), ["hooks/a.sh"])
        self.assertNotIn("more.", reason)

    def test_an_absurdly_wide_numeric_knob_does_not_leak_to_stderr(self):
        """All-digits is not enough: `[ x -lt y ]` prints "integer expected" for a value
        wider than intmax_t, so a twenty-digit knob passed the digit guard and still made
        the hook write to stderr."""
        self.commit({"hooks/a.sh": "#!/bin/sh\necho bye\n"})
        wide = "9" * 20
        for knob in ("DOC_GATE_MAX_NAMED", "DOC_GATE_MAX_COMMITS"):
            with self.subTest(knob=knob):
                r = self.push(session="wide-" + knob, **{knob: wide})
                self.assertEqual(r.stderr, "")
                self.assertIn("hooks/a.sh", self.assert_denied(r))

    def test_a_max_named_of_zero_with_several_files_names_one_and_counts_the_rest(self):
        self.commit({"hooks/a.sh": "1\n", "hooks/b.sh": "2\n", "hooks/c.sh": "3\n"})
        reason = self.assert_denied(self.push(DOC_GATE_MAX_NAMED="0"))
        self.assertEqual(len(re.findall(r"^    - ", reason, re.M)), 1, reason)
        self.assertIn("... and 2 more.", reason)

    # ============================================ the segment split and quoted reasons
    def test_a_quoted_override_reason_containing_a_semicolon_is_still_recorded(self):
        """ISSUE #28, AND IT WAS A SILENT BYPASS RATHER THAN A WRONG ANSWER.

        The command text was split into segments with `tr ';&|()' '\\n\\n\\n\\n\\n'`, which
        splits on those bytes wherever they appear -- inside the quoted override reason
        included. `DOC_GATE_OVERRIDE="rename only; no behaviour change" git push` became
        `DOC_GATE_OVERRIDE="rename only` and ` no behaviour change" git push`; PUSH_RE
        anchors at a segment start and neither segment starts with an assignment run
        followed by `git`, so NO push was found, the script exited 0, and a code-only
        push went through with no deny AND NO OVERRIDE ROW.

        That is the one way to take the escape hatch without being counted, and being
        counted is the entire reason the hatch is shaped the way it is. So the two things
        asserted here are that the push still goes through AND that the row exists."""
        self.commit({"hooks/a.sh": "#!/bin/sh\necho bye\n"})
        reason = "rename only; no behaviour change"
        self.assert_allowed(self.push('DOC_GATE_OVERRIDE="%s" git push' % reason))
        rows = self.overrides()
        self.assertEqual(len(rows), 1, "the escape was taken and never counted: %r" % rows)
        self.assertEqual(rows[0]["kind"], "inline")
        self.assertEqual(rows[0]["reason"], reason)

    def test_every_splitting_character_inside_a_quoted_reason(self):
        """`;` is the one that was reported. A reason is PROSE, so parentheses and
        ampersands are ordinary in it too, and each was the same bypass."""
        cases = ["rename only; no behaviour change",
                 "chore & vendor bump",
                 "docs live upstream | nothing to add here",
                 "revert (see the incident note)",
                 "a;b&c|d(e)f"]
        for i, reason in enumerate(cases):
            with self.subTest(reason=reason):
                self.setUp()
                self.commit({"hooks/a.sh": "#!/bin/sh\necho bye %d\n" % i})
                self.assert_allowed(self.push('DOC_GATE_OVERRIDE="%s" git push' % reason))
                rows = self.overrides()
                self.assertEqual(len(rows), 1, rows)
                self.assertEqual(rows[0]["reason"], reason)

    def test_the_same_push_without_the_override_is_still_denied(self):
        """NON-VACUITY for all of the above: the commit really does trigger the gate, so
        `assert_allowed` there is the override working rather than the gate sleeping."""
        self.commit({"hooks/a.sh": "#!/bin/sh\necho bye\n"})
        self.assertIn("hooks/a.sh", self.assert_denied(self.push()))

    def test_an_unquoted_separator_still_splits(self):
        """The split is still a split. A push buried in a chain is what the segmenting
        exists for, and a quote-aware version that stopped splitting at all would pass
        every test above while retiring the gate."""
        self.commit({"hooks/a.sh": "#!/bin/sh\necho bye\n"})
        # A DISTINCT SESSION PER CASE, not a distinct tool_use_id. The gate refuses one
        # HEAD once per session and then fails open, so a loop that varied only the id
        # measured the deny for the first command and the once-per-session guard for
        # every one after it -- three failures that looked like a broken splitter.
        for i, cmd in enumerate(["echo hi; git push",
                                 "echo hi && git push",
                                 "echo hi | cat; git push origin HEAD",
                                 "(cd . && git push)"]):
            with self.subTest(command=cmd):
                self.assertIn("hooks/a.sh",
                              self.assert_denied(self.push(cmd, session="split%d" % i,
                                                           tool_use_id="tu%d" % i)))

    def test_a_quoted_separator_does_not_manufacture_a_push(self):
        """The other direction of the same rule: text that only LOOKS like a push once
        the quotes are ignored must not be gated. `git commit -m "...; git push"` writes
        to no remote."""
        self.commit({"hooks/a.sh": "#!/bin/sh\necho bye\n"})
        self.assert_allowed(self.push('git commit -m "fix; git push later"'),
                            "a push named inside a commit message is not a push")

    # ================================================================ script hygiene
    def test_the_script_parses_and_is_brace_wrapped(self):
        """House rule: the whole body is one brace group, `exit` before the closing `}`,
        so a `git pull` cannot execute half a rewritten file that is already running."""
        r = subprocess.run(["bash", "-n", HOOK], capture_output=True, text=True,
                           stdin=subprocess.DEVNULL, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        lines = [l.rstrip() for l in hook_text().splitlines() if l.strip()]
        self.assertEqual(lines[-1].strip(), "}")
        self.assertTrue(lines[-2].strip().startswith("exit"), lines[-2])

    def test_every_env_knob_is_documented_in_the_header(self):
        text = hook_text()
        header = text.split("set -uo pipefail")[0]
        knobs = set(re.findall(r'\$\{(DOC_GATE[A-Z_]*|SKILL_COMPOUNDER_DOC_GATE)', text))
        knobs.add("DOC_GATE_OVERRIDE")
        self.assertIn("SKILL_COMPOUNDER_DOC_GATE", knobs)
        for knob in sorted(knobs):
            self.assertIn(knob, header, "%s is undocumented" % knob)

    def test_the_home_guard_precedes_the_first_expansion(self):
        """`set -u` plus an unset HOME aborts a hook before it prints anything."""
        text = hook_text()
        lines = text.split("\n")
        guard = next(i for i, l in enumerate(lines) if l.strip() == ': "${HOME:=/tmp}"')
        first = next(i for i, l in enumerate(lines)
                     if "$HOME" in l and not l.lstrip().startswith("#"))
        self.assertLess(guard, first)

    def test_the_script_is_executable(self):
        self.assertTrue(os.access(HOOK, os.X_OK))

    def test_the_session_id_is_sanitised_with_the_shared_expression(self):
        """One event sanitised two ways becomes two claims under two spellings, and the
        double delivery then goes through both."""
        text = hook_text()
        self.assertIn("tr -c 'A-Za-z0-9._-' '_' | cut -c1-96", text)

    def test_an_awkward_session_id_still_produces_exactly_one_deny(self):
        """The sanitiser has to be exercised, not only grepped for."""
        self.commit({"hooks/a.sh": "#!/bin/sh\necho bye\n"})
        sid = "../../etc/pa sswd/" + ("z" * 200)
        self.assert_denied(self.push(session=sid, tool_use_id="tu1"))
        self.assert_allowed(self.push(session=sid, tool_use_id="tu2"))
        self.assertEqual("", self.push(session=sid, tool_use_id="tu3").stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
