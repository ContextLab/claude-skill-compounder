#!/usr/bin/env python3
"""What the reuse check is given: `find` ranked by how rare a word is, the floor a
candidate must reach before a model is asked about it, and the memo that keeps a
repeated request from being judged twice.

The store below is modelled on a real one of about forty lessons and skills: the
names are real, the texts were written for this test and keep the shape that made the
real ranking fail (a skill with a long body that holds a little of every subject, and
lessons that share only everyday words with a request)."""

import json
import os
import subprocess
import unittest

from test_support import NOW, Case, surfer_reachable

LESSONS = [
    ("patch-scripts-match-current-text",
     "Use when editing files with a Python patch script that does exact-string replacement.",
     "A patch script written against an older copy of a file fails its assert, or changes nothing. Read the "
     "current text first, and assert that each replacement matched exactly once.\n"),
    ("zsh-equals-word",
     "Use when a zsh command line prints a separator with a bare word starting with an equals sign.",
     "zsh expands the word as a command lookup and the chain fails with not found. Quote the separator.\n"),
    ("zsh-nomatch-glob",
     "Use when a zsh command has an unquoted glob that may match nothing.",
     "zsh stops with no matches found before the command runs. Quote the glob, as in grep --include='*.py'.\n"),
    ("macos-no-timeout",
     "Use when wrapping a command in timeout on macOS.",
     "macOS ships no timeout command, so the call fails with command not found. Use the Bash tool's own "
     "timeout, or gtimeout from coreutils.\n"),
    ("heredoc-ends-and-chain",
     "Use when a Bash command has a heredoc inside a chain that gates a commit.",
     "The lines after the heredoc's end marker are a new command list, so the chain no longer gates them. "
     "Close the heredoc, then start a new call.\n"),
    ("chain-commit-with-and",
     "Use when a Bash command runs a patch or a test and then git commit in the same call.",
     "Join the steps with && and never with a semicolon, so a failed step stops the commit.\n"),
    ("gate-commit-on-pass-line",
     "Use when a git commit is chained after a test whose output is piped through tail.",
     "A pipeline exits with its last command, so the commit runs after a failed test. Write the output to a "
     "file and grep it for the pass line.\n"),
    ("shared-tree-no-add-all-no-stash",
     "Use when running git add or git stash in a working tree that parallel subagents are writing to.",
     "Add only the paths you changed, by name, and never stash: the stack is shared and a pop takes another "
     "agent's files.\n"),
    ("state-no-mocks-in-agent-prompts",
     "Use when dispatching a subagent to write or verify tests.",
     "Say in the prompt that tests use real files and real calls. An agent that is not told writes mocks.\n"),
    ("agent-worktree-check-base",
     "Use when dispatching an agent with worktree isolation.",
     "The worktree may start from an older commit. Have the agent print the base commit and reset to the "
     "branch it was meant to start from.\n"),
    ("sed-range-from-empty-variable",
     "Use when computing a sed line range from a shell variable holding a grep result.",
     "An empty result makes the range start at a negative line and sed prints an error. Test the variable "
     "before the arithmetic.\n"),
    ("kill-script-leaves-children",
     "Use when stopping a long-running shell script in order to relaunch it.",
     "Killing the script leaves its children running. Kill the process group, then check with pgrep.\n"),
    ("verify-push-with-ls-remote",
     "Use when checking that a git push reached the remote.",
     "Ask the remote with git ls-remote origin and compare the commit. A local tracking ref can be stale.\n"),
    ("codex-exec-usage-limit",
     "Use when running a long codex exec review round that may hit the account usage limit.",
     "Check the log for the usage limit message before reading the round as finished.\n"),
]
SKILLS = [
    ("speckit-execute",
     "Run the full Spec Kit pipeline (plan, tasks, analyze, implement) on the active spec and fix every analyze "
     "finding.",
     "Work through the pipeline in order. First read the current spec, then plan, then generate the tasks. "
     "Analyze the result for quality and consistency, research every finding, and fix it before you implement. "
     "Implement every task with tests, with no shortcuts, and verify each one: a handful of spot checks is not "
     "enough. Review the code for performance, for security and for the experience of the user who installs "
     "the package, and audit the result against the spec a few times. Use the skills and tools that are "
     "available. Make the release notes when the version is ready, and come back to anything left open.\n"),
    ("history-surfer",
     "Use when the user wants to recall, search or reference their own past prompts, for example what they "
     "asked earlier. Do not use it for searching code or files.",
     "Query the local prompt log with the surfer command. It can list the current project's prompts, show one "
     "in full and search across every project. Review what was found before quoting it.\n"),
    ("cdl-bib-cite",
     "Use when filling a placeholder citation or adding a reference to a paper whose bibliography is a shared "
     "BibTeX file.",
     "Search the bibliography for the paper first. Add the missing entry, then verify it with the checker.\n"),
    ("bib-duplicate-check",
     "Use when adding entries to an existing BibTeX bibliography, especially a large or shared one.",
     "Create no new entry before searching for the same paper under another key. Audit the keys afterwards.\n"),
]

# The owner's request as the audit quotes it, with the rest of a long request written in
# the same manner. The reuse check answered it with `speckit-execute`.
RELEASE_AUDIT = (
    "first create a new release (v0.4) for the current version of the code.\n\n"
    "then do a careful (ultrawork) audit of the package and come up with a few things we can do to make it even "
    "more awesome and slick:\n - improvements to the interface\n - performance improvements\n - a better user "
    "experience (easier to use, better results)\n - higher quality lessons\n - an easier install and uninstall\n"
    " - a handful of carefully researched and tested general skills and tools that are useful to a wide range "
    "of users")
# The scripted request twelve of the thirteen checks ran on, with the words its `reuse`
# events logged. It was answered with `patch-scripts-match-current-text`, and later with
# `zsh-nomatch-glob`, `shared-tree-no-add-all-no-stash` and `state-no-mocks-in-agent-prompts`.
SECURITY_REVIEW = (
    "Review this change for security vulnerabilities. The files that changed are listed below, read these: "
    "dev/demo.sh, hooks/register.ts, hooks/judge.ts, bin/compound, install.sh, notes/, tests/test_install.py")
OFFERED_WRONGLY = {"patch-scripts-match-current-text", "zsh-nomatch-glob", "shared-tree-no-add-all-no-stash",
                   "state-no-mocks-in-agent-prompts", "speckit-execute"}
# (the request, the entry that covers it)
COVERED = [
    ("Write a Python patch script that replaces the old function signature in every file with exact-string "
     "replacement and asserts that each replacement matched.", "patch-scripts-match-current-text"),
    ("Run the full Spec Kit pipeline on the active spec: plan, tasks, analyze and implement, and fix every finding "
     "that analyze reports.", "speckit-execute"),
    ("What did I ask earlier about the plotting backends? Search my past prompts in every project and show me the "
     "prompt in full.", "history-surfer"),
    ("Fill in the placeholder citations in the introduction of the paper and add the missing references to the "
     "bibliography.", "cdl-bib-cite"),
    ("Dispatch three subagents in worktrees to write and verify the tests for the parser, and tell each one which "
     "branch to start from.", "state-no-mocks-in-agent-prompts"),
    ("Wrap the integration tests in a timeout of five minutes so that a hung test cannot block the run on macOS.",
     "macos-no-timeout"),
]


class Store(Case):
    def setUp(self):
        Case.setUp(self)
        for name, when, body in LESSONS:
            self.box.write_lesson(self.box.lesson_dir(name, "user"), name, description=when, body=body)
        for name, when, body in SKILLS:
            self.box.write_lesson(self.box.skill_dir(name, "user"), name, description=when, body=body)

    def request(self, text, *flags, **kw):
        return self.box.json("find", "--request", "--json", *flags, stdin=text, **kw)

    def names(self, data):
        return [row["name"] for row in data["items"]]


class RankingTest(Store):
    def test_a_rare_word_counts_for_more_than_two_everyday_ones(self):
        """`bash` and `command` are each in several entries, `worktree` in one. By the
        count of words the two-word matches came first."""
        data = self.box.json("find", "bash", "command", "worktree", "--json")
        rows = {row["name"]: row for row in data["items"]}
        self.assertEqual(self.names(data)[0], "agent-worktree-check-base")
        self.assertEqual(rows["agent-worktree-check-base"]["score"], 1, "`score` stays the number of words matched")
        self.assertEqual(rows["chain-commit-with-and"]["score"], 2)
        self.assertGreater(rows["agent-worktree-check-base"]["weight"], rows["chain-commit-with-and"]["weight"])
        self.assertEqual(self.names(self.box.json("find", "heredoc", "--json"))[0], "heredoc-ends-and-chain")

    def test_a_word_every_entry_carries_counts_for_nothing(self):
        """Nearly all eighteen say `Use when`: by the count of words each of them matched
        two of two."""
        data = self.box.json("find", "use", "when", "--json", "--limit", "50")
        self.assertTrue(all(row["weight"] <= 0.02 for row in data["items"]), [row["weight"] for row in data["items"]])
        data = self.box.json("find", "use", "when", "heredoc", "--json")
        self.assertEqual((data["items"][0]["name"], data["items"][0]["score"]), ("heredoc-ends-and-chain", 3))
        self.assertGreater(data["items"][0]["weight"], 50 * data["items"][1]["weight"])

    def test_word_forms_match(self):
        """The audit's miss: `find heredocs chained` did not return the heredoc lesson."""
        self.assertEqual(self.names(self.box.json("find", "heredocs", "chained", "--json"))[0], "heredoc-ends-and-chain")
        for form in ("install", "installs", "installing", "installed"):
            self.assertIn("speckit-execute", self.names(self.box.json("find", form, "--json")), form)
        for form in ("dispatch", "dispatches", "dispatched", "dispatching"):
            self.assertEqual(set(self.names(self.box.json("find", form, "--json"))),
                             {"state-no-mocks-in-agent-prompts", "agent-worktree-check-base"}, form)
        for form in ("citation", "citations", "replacement", "replacements", "matches", "matching"):
            self.assertTrue(self.box.json("find", form, "--json")["items"], form)

    def test_the_name_and_description_count_for_more_than_the_body(self):
        data = self.box.json("find", "timeout", "--json")
        self.assertEqual(self.names(data)[0], "macos-no-timeout")
        data = self.box.json("find", "security", "--json")
        row = data["items"][0]
        self.assertEqual((row["name"], row["matched"]), ("speckit-execute", ["security"]))
        self.assertLess(row["weight"], 1.0, "a word found only in the body is half a word")

    def test_a_long_body_cannot_add_up_to_a_match(self):
        """`speckit-execute` holds seven of these words in its body and none in its name
        or description; the body counts for at most one whole word."""
        words = ["release", "audit", "performance", "experience", "quality", "handful", "version"]
        row = self.box.json("find", *(words + ["--json"]))["items"][0]
        self.assertEqual((row["name"], row["score"]), ("speckit-execute", 7))
        self.assertLessEqual(row["weight"], 1.0)

    def test_each_row_says_how_it_matched(self):
        row = self.box.json("find", "heredocs", "xylophone", "chained", "--json")["items"][0]
        self.assertEqual(row["matched"], ["heredocs", "chained"])
        self.assertEqual(row["score"], 2)
        self.assertIsInstance(row["weight"], float)
        proc = self.box.run("find", "heredocs", "xylophone", "chained")
        self.assertIn("lesson heredoc-ends-and-chain (user) [2 of 3 words: heredocs, chained]: Use when a Bash",
                      proc.stdout)
        self.assertNotIn("/3 words]", proc.stdout)


class RequestTest(Store):
    def test_what_the_reuse_check_offered_wrongly_is_no_longer_a_candidate(self):
        for text in (RELEASE_AUDIT, SECURITY_REVIEW):
            data = self.request(text)
            self.assertEqual(set(self.names(data)) & OFFERED_WRONGLY, set(), text[:40])
        self.assertEqual(self.names(self.request(SECURITY_REVIEW)), [])
        # One entry still reaches the floor by chance: its description says `range` and
        # `result`, and the request "a wide range of users" and "better results". The floor
        # thins the candidates; whether one covers the request is the judge's to say.
        self.assertEqual(self.names(self.request(RELEASE_AUDIT)), ["sed-range-from-empty-variable"])

    def test_without_the_floor_they_are_all_there(self):
        """The floor is what removes them: at 0 every entry that shares a word comes back."""
        data = self.request(RELEASE_AUDIT, "--floor", "0", "--limit", "50")
        self.assertIn("speckit-execute", self.names(data))
        self.assertGreater(len(data["items"]), 5)
        self.assertTrue(all(0 < row["weight"] for row in data["items"]),
                        [(row["name"], row["weight"]) for row in data["items"]])

    def test_what_covers_a_request_is_still_found_and_ranked_first(self):
        for text, name in COVERED:
            data = self.request(text)
            self.assertIn(name, self.names(data), text)
            self.assertEqual(self.names(data)[0], name, [(r["name"], r["weight"]) for r in data["items"]])
            self.assertLessEqual(len(data["items"]), 4, "the judge is shown a few candidates, not the store")

    def test_a_candidate_far_below_the_best_one_is_dropped(self):
        """Beside an entry that shares ten words with a request, one that shares two is
        there by chance: a candidate needs a third of the best one's weight."""
        text = COVERED[0][0]
        every = self.request(text, "--floor", "0", "--limit", "50")["items"]
        best = every[0]["weight"]
        self.assertTrue([row for row in every if 0.5 <= row["weight"] < best / 3], "the store holds such entries")
        kept = self.request(text, "--floor", "0.5", "--limit", "50")["items"]
        self.assertEqual([row["name"] for row in kept], [COVERED[0][1]])
        # Two entries that both cover a request both stay.
        both = self.request(COVERED[4][0])
        self.assertEqual(self.names(both), ["state-no-mocks-in-agent-prompts", "agent-worktree-check-base"])

    def test_the_search_words_are_the_rare_ones(self):
        """The audit: the first ten words in order included `come`, `few` and `awesome`."""
        words = self.request(RELEASE_AUDIT)["words"]
        self.assertEqual(len(words), 10)
        for word in ("current", "careful", "come", "few", "awesome", "first", "then", "make"):
            self.assertNotIn(word, words)
        for word in ("release", "ultrawork", "slick", "interface"):
            self.assertIn(word, words)
        self.assertEqual(words, self.request(RELEASE_AUDIT)["words"], "the same request, the same words")

    def test_the_floor_is_a_flag_and_a_setting(self):
        text = COVERED[5][0]
        self.assertEqual(self.request(text)["floor"], 1.5)
        self.assertEqual(self.request(text, COMPOUND_REUSE_FLOOR="0.25")["floor"], 0.25)
        self.assertEqual(self.request(text, "--floor", "3", COMPOUND_REUSE_FLOOR="0.25")["floor"], 3.0)
        self.assertEqual(self.request(text, COMPOUND_REUSE_FLOOR="nonsense")["floor"], 1.5, "a bad value is the default")
        self.assertEqual(self.request(text, COMPOUND_REUSE_FLOOR="-1")["floor"], 1.5)
        self.assertEqual(self.names(self.request(text, "--floor", "50")), [])
        self.assertGreater(len(self.request(text, "--floor", "0")["items"]), len(self.request(text)["items"]))
        self.assertExit(self.box.run("find", "--request", "--floor", "-2", stdin=text), 2)
        self.assertExit(self.box.run("find", "--request", "--floor", "many", stdin=text), 2)

    def test_typed_words_have_no_floor(self):
        data = self.box.json("find", "security", "--json")
        self.assertEqual(self.names(data), ["speckit-execute"])
        self.assertEqual(data["floor"], 0)
        self.assertEqual(self.names(self.box.json("find", "security", "--floor", "1", "--json")), [])

    def test_a_request_is_read_from_stdin_and_only_there(self):
        self.assertExit(self.box.run("find", "--request", stdin=""), 2)
        self.assertExit(self.box.run("find", "--request", stdin="  \n"), 2)
        # A request with no word in it is a request with no candidate, not an error.
        for wordless in ("!!! ... ???", "12345 67890 2026", "the and for with"):
            data = self.request(wordless)
            self.assertEqual((data["words"], data["items"], data["prompts"]), ([], [], []), wordless)
            self.assertExit(self.box.run("find", "--request", stdin=wordless), 0)
        proc = self.box.run("find", "--request", "timeout", stdin="wrap it in a timeout")
        self.assertExit(proc, 2)
        self.assertIn("--request", proc.stderr)
        proc = self.box.run("find", "--request", stdin=COVERED[5][0])
        self.assertExit(proc, 0)
        self.assertIn("lesson macos-no-timeout (user) [", proc.stdout)

    def test_the_packages_own_procedures_are_never_candidates(self):
        self.box.write_lesson(self.box.skill_dir("reuse", "general"), "reuse",
                              description="Use when starting a substantial task: a script, a tool, a pipeline.",
                              body="Check for existing lessons, skills and scripts before building.\n")
        data = self.request("Write a script and a tool that builds the pipeline for the substantial task.", "--floor", "0")
        self.assertNotIn("reuse", self.names(data))


class RequestPromptLogTest(Store):
    """Earlier requests in request mode, against the real history-surfer."""

    def test_an_earlier_request_must_share_the_rare_words(self):
        if not surfer_reachable():
            self.skipTest("history-surfer cannot be cloned from here")
        box = self.box
        box.plugin()
        self.assertExit(box.run("install", "--bin-dir", box.bin, COMPOUND_NO_SURFER=None), 0)
        surfer = os.path.join(box.bin, "surfer")
        other = os.path.join(box.root, "other-project")
        os.makedirs(other)
        filler = " ".join("paragraph %d of a long pasted review about the project" % n for n in range(40))
        rows = [
            # Asked for the same thing.
            ("s1", 1789000000000, other, "cut the v0.3 release and then audit the package for slick interface improvements"),
            # Shares the everyday words (`current`, `version`, `code`, `few`, `make`) and no rare one.
            ("s2", 1789000100000, other, "let's take a step back: can you help me understand the current version of "
                                         "the code and come up with a few ways to make it simpler"),
            # A long pasted text that holds the rare words far beyond what is shown of it.
            ("s3", 1789000200000, other, "The project is up and running locally. " + filler +
             " release audit package interface performance experience quality slick ultrawork"),
            ("s4", 1789000300000, other, "what is the release date"),
        ]
        with open(os.path.join(box.claude, "history.jsonl"), "w") as handle:
            for session, stamp, project, text in rows:
                handle.write(json.dumps({"display": text, "pastedContents": {}, "timestamp": stamp,
                                         "project": project, "sessionId": session}) + "\n")
        env = box.env(PATH=box.bin + ":/usr/bin:/bin")
        seeded = subprocess.run([surfer, "import-history"], env=env, cwd=box.project, stdin=subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
        self.assertEqual(seeded.returncode, 0, seeded.stderr)

        data = self.request(RELEASE_AUDIT, PATH=box.bin + ":/usr/bin:/bin")
        self.assertEqual(data["surfer"], "ok")
        self.assertEqual([hit["session"] for hit in data["prompts"]], ["s1"],
                         [(hit["session"], hit["score"], hit["weight"]) for hit in data["prompts"]])
        hit = data["prompts"][0]
        self.assertGreaterEqual(hit["score"], 4)
        self.assertGreaterEqual(hit["weight"], 0.34, "its share of the weight of the search words")
        typed = box.json("find", "release", "--json", PATH=box.bin + ":/usr/bin:/bin")
        self.assertEqual(sorted(hit["session"] for hit in typed["prompts"]), ["s1", "s4"],
                         "typed words have no floor, and still match only what is shown of a prompt")


class MemoTest(Store):
    TEXT = COVERED[5][0]

    def put(self, key, verdict="nothing", items=(), prompts=(), **kw):
        return self.box.run("memo", stdin=json.dumps({"key": key, "verdict": verdict, "items": list(items),
                                                      "prompts": list(prompts)}), **kw)

    def test_a_request_has_a_key_and_nothing_remembered_at_first(self):
        data = self.request(self.TEXT)
        self.assertRegex(data["memo_key"], r"^[0-9a-f]{32}$")
        self.assertNotIn("memo", data)
        self.assertEqual(self.request(self.TEXT)["memo_key"], data["memo_key"])
        self.assertFalse(os.path.exists(os.path.join(self.box.chome, "memo.json")), "asking writes nothing")
        self.assertNotIn("memo_key", self.box.json("find", "timeout", "--json"), "typed words are not a request")

    def test_a_verdict_is_remembered_for_the_same_request_project_and_store(self):
        key = self.request(self.TEXT)["memo_key"]
        earlier = {"id": "older:1", "ts": "2026-09-01T12:00:00Z", "project": "/p", "session": "older",
                   "prompt": "wrap the tests in a timeout"}
        self.assertExit(self.put(key, "named", ["macos-no-timeout"], [earlier]), 0)
        self.assertTrue(os.path.isfile(os.path.join(self.box.chome, "memo.json")), "it lives under COMPOUND_HOME")
        data = self.request(self.TEXT)
        self.assertEqual(data["memo"]["verdict"], "named")
        self.assertEqual(data["memo"]["items"], ["macos-no-timeout"])
        self.assertEqual(data["memo"]["prompts"], [earlier])
        self.assertEqual(data["prompts"], [])
        self.assertEqual(data["surfer"], "memo", "a remembered request does not search the prompt log again")
        self.assertEqual(self.names(data)[0], "macos-no-timeout", "the candidates are still listed")
        # White space is not a different request; another word is.
        self.assertIn("memo", self.request("  " + self.TEXT.replace(" ", "  ") + "\n"))
        self.assertNotIn("memo", self.request(self.TEXT + " Please."))
        # Another project asks for itself.
        elsewhere = os.path.join(self.box.root, "elsewhere")
        os.makedirs(elsewhere)
        self.assertNotIn("memo", self.request(self.TEXT, COMPOUND_PROJECT=elsewhere))
        # Another floor is another question.
        self.assertNotIn("memo", self.request(self.TEXT, "--floor", "0.5"))

    def test_a_change_to_the_store_forgets_it(self):
        key = self.request(self.TEXT)["memo_key"]
        self.assertExit(self.put(key), 0)
        self.assertEqual(self.request(self.TEXT)["memo"]["verdict"], "nothing")
        self.box.add("gtimeout-from-coreutils", "Use when a script needs a timeout command on macOS.",
                     "brew install coreutils provides gtimeout. Call it by that name in the script.\n")
        data = self.request(self.TEXT)
        self.assertNotIn("memo", data)
        self.assertNotEqual(data["memo_key"], key)
        self.assertExit(self.put(data["memo_key"], "named", ["gtimeout-from-coreutils"]), 0)
        self.assertIn("memo", self.request(self.TEXT))
        proc = self.box.run("add", "--update", "--name", "gtimeout-from-coreutils", "--body",
                            "brew install coreutils provides gtimeout and gdate. Call each by that name in a script.\n")
        self.assertExit(proc, 0)
        self.assertNotIn("memo", self.request(self.TEXT), "a rewritten lesson is a changed store")
        self.assertExit(self.box.run("rm", "gtimeout-from-coreutils"), 0)
        back = self.request(self.TEXT)
        self.assertEqual((back["memo_key"], back["memo"]["verdict"]), (key, "nothing"),
                         "the store as it was is the store that was judged")
        os.makedirs(os.path.join(self.box.project, "scripts"))
        before = self.request(self.TEXT)["memo_key"]
        with open(os.path.join(self.box.project, "scripts", "run_with_timeout.sh"), "w") as handle:
            handle.write("#!/bin/sh\n# Run a command under a timeout on macOS.\n")
        self.assertNotEqual(self.request(self.TEXT)["memo_key"], before, "a new script is a changed store")

    def test_it_is_bounded_and_the_oldest_go_first(self):
        key = self.request(self.TEXT)["memo_key"]
        self.assertExit(self.put(key, COMPOUND_NOW=NOW), 0)
        for n in range(210):
            self.assertExit(self.put("%032x" % n, COMPOUND_NOW=NOW + 1 + n), 0)
        with open(os.path.join(self.box.chome, "memo.json")) as handle:
            held = json.load(handle)["entries"]
        self.assertEqual(len(held), 200)
        self.assertNotIn(key, held)
        self.assertNotIn("%032x" % 5, held)
        self.assertIn("%032x" % 209, held)
        self.assertNotIn("memo", self.request(self.TEXT))

    def test_it_is_not_kept_for_ever(self):
        key = self.request(self.TEXT)["memo_key"]
        self.assertExit(self.put(key), 0)
        self.assertIn("memo", self.request(self.TEXT, COMPOUND_NOW=NOW + 6 * 86400))
        self.assertNotIn("memo", self.request(self.TEXT, COMPOUND_NOW=NOW + 8 * 86400))

    def test_what_is_not_a_verdict_is_refused_and_writes_nothing(self):
        key = self.request(self.TEXT)["memo_key"]
        for stdin in ("", "not json", "[]", json.dumps({"key": key}), json.dumps({"key": "short", "verdict": "nothing"}),
                      json.dumps({"key": key, "verdict": "unanswered"}),
                      json.dumps({"key": key, "verdict": "named", "items": "macos-no-timeout"}),
                      json.dumps({"key": key, "verdict": "named", "items": [], "prompts": ["r1"]})):
            proc = self.box.run("memo", stdin=stdin)
            self.assertExit(proc, 2)
        self.assertFalse(os.path.exists(os.path.join(self.box.chome, "memo.json")))

    def test_a_memo_file_that_does_not_read_is_no_memo_and_no_error(self):
        os.makedirs(self.box.chome, exist_ok=True)
        path = os.path.join(self.box.chome, "memo.json")
        for text in ("{ not json", "[]", json.dumps({"entries": []}), json.dumps({"entries": {"k": "v"}})):
            with open(path, "w") as handle:
                handle.write(text)
            data = self.request(self.TEXT)
            self.assertNotIn("memo", data)
            self.assertExit(self.put(data["memo_key"]), 0)
            self.assertEqual(self.request(self.TEXT)["memo"]["verdict"], "nothing")

    def test_a_long_remembered_text_is_cut(self):
        key = self.request(self.TEXT)["memo_key"]
        many = [{"id": "s:%d" % n, "ts": "", "project": "/p", "session": "s", "prompt": "x" * 5000} for n in range(40)]
        self.assertExit(self.put(key, "named", ["n%d" % n for n in range(100)], many), 0)
        memo = self.request(self.TEXT)["memo"]
        self.assertLessEqual(len(memo["items"]), 20)
        self.assertLessEqual(len(memo["prompts"]), 10)
        self.assertTrue(all(len(row["prompt"]) <= 300 for row in memo["prompts"]))

    def test_purge_takes_the_memo_with_the_rest(self):
        self.assertExit(self.put(self.request(self.TEXT)["memo_key"]), 0)
        proc = self.box.run("uninstall", "--purge")
        self.assertExit(proc, 0)
        self.assertFalse(os.path.exists(self.box.chome), proc.stdout + proc.stderr)


if __name__ == "__main__":
    unittest.main()
