#!/usr/bin/env python3
"""No secret reaches the event log or the memo, whoever writes it.

The mod masks a call and its error before it logs them (hooks/safe.ts). The CLI holds the
same masking and applies it where an event or a memo entry is WRITTEN, so a field the mod
did not mask, an event another program hands to `compound log`, and an event a command of
the CLI writes itself (`skip --why`) are all masked, and every text is cut at a cap.
"""

import json
import os
import unittest

from test_support import NOW, Case

BEARER = "abcdefghijklmnopqrstuvwxyz0123456789ABCD"
# Made of two halves so that no key-shaped literal sits in the repository: the value is
# the example key of the AWS documentation, and a secret scanner cannot tell.
AWS = "wJalrXUtnFEMI/K7MDENG/" + "bPxRfiCYEXAMPLEKEY"
PASSWORD = "s3cr3tPassw0rdXyZ"
GITHUB = "ghp_" + "A1b2C3d4E5" * 3 + "ZZ"
SECRETS = (BEARER, AWS, PASSWORD, GITHUB)

CURL = "curl -H 'Authorization: Bearer %s' https://api.example.invalid/v1/items" % BEARER
ENVCMD = "AWS_SECRET_ACCESS_KEY=%s aws s3 ls s3://bucket" % AWS
CLONE = "git clone https://deploy:%s@git.example.invalid/team/repo.git" % PASSWORD
TOKEN = "gh api user -H 'X-Note: none' # with %s in a comment" % GITHUB
CALLS = (CURL, ENVCMD, CLONE, TOKEN)


class RedactionCase(Case):
    def files(self):
        out = {}
        for name in ("events.jsonl", "memo.json"):
            path = os.path.join(self.box.chome, name)
            if os.path.exists(path):
                with open(path, encoding="utf-8") as handle:
                    out[name] = handle.read()
        return out

    def outputs(self):
        out = {}
        for args in (("events",), ("events", "--json"), ("events", "--unsettled", "--json"), ("status",),
                     ("status", "--json"), ("report",), ("report", "--json")):
            proc = self.box.run(*args)
            out[" ".join(args)] = proc.stdout + proc.stderr
        return out

    def assertNoSecret(self):
        seen = dict(self.files())
        seen.update(self.outputs())
        self.assertIn("events.jsonl", seen)
        for where, text in sorted(seen.items()):
            for secret in SECRETS:
                self.assertNotIn(secret, text, "%s holds a secret" % where)
        return seen


class LogRedactionTest(RedactionCase):
    def test_every_free_text_field_the_mod_logs_is_masked_when_it_is_written(self):
        """Each event type that carries a call, an error or a reason, sent to the real
        `compound log` UNMASKED, as a mod that forgot to mask would send it."""
        error = "Exit code 1\nfatal: could not read from %s\n%s" % (CLONE, CURL)
        events = [
            {"type": "guard", "lesson": "x", "tool": "Bash", "text": CURL, "ms": 3},
            {"type": "retry", "lessons": ["x"], "tool": "Bash", "same": False, "text": ENVCMD},
            {"type": "recall", "lesson": "x", "tool": "Bash", "call": CLONE, "error": error, "at": "failure"},
            {"type": "capture", "tool": "Bash", "failed": CURL, "error": error, "fixed": ENVCMD, "evidence": TOKEN,
             "call": "toolu_01", "agent": None},
            {"type": "judge", "moment": "fix", "verdict": "none", "ms": 5, "reason": "it ran " + TOKEN},
            {"type": "error", "where": "capture.parse", "message": "haiku answered something unreadable: " + CLONE},
            {"type": "reuse", "lessons": ["x"], "prompts": ["s1:1"], "words": ["deploy", GITHUB]},
            {"type": "refuse", "why": "debt", "debts": ["toolu_01"]},
            {"type": "remind", "captures": ["ab12cd34"], "note": {"nested": [CURL, {"deeper": ENVCMD}]}},
        ]
        for event in events:
            self.box.log(event)
        seen = self.assertNoSecret()
        logged = self.box.read_events()
        self.assertEqual([event["type"] for event in logged], [event["type"] for event in events])
        # What is not secret is kept, so the event still says what happened.
        capture = logged[3]
        self.assertEqual(capture["failed"], "curl -H 'Authorization: Bearer <redacted>' https://api.example.invalid/v1/items")
        self.assertEqual(capture["fixed"], "AWS_SECRET_ACCESS_KEY=<redacted> aws s3 ls s3://bucket")
        self.assertIn("git clone https://<redacted>@git.example.invalid/team/repo.git", capture["error"])
        self.assertIn("<redacted>", capture["evidence"])
        self.assertEqual(logged[1]["text"], "AWS_SECRET_ACCESS_KEY=<redacted> aws s3 ls s3://bucket")
        self.assertIn("<redacted>", seen["events --json"])

    def test_what_a_command_of_the_cli_writes_itself_is_masked_too(self):
        self.box.log({"type": "capture", "id": "cap-1", "failed": "./deploy.sh", "fixed": "./deploy.sh --target x"})
        proc = self.box.run("skip", "--why", "the fix was only %s and nothing else" % ENVCMD)
        self.assertExit(proc, 0)
        self.assertNotIn(AWS, proc.stdout)
        self.assertNoSecret()
        skip = self.box.read_events()[-1]
        self.assertEqual(skip["why"], "the fix was only AWS_SECRET_ACCESS_KEY=<redacted> aws s3 ls s3://bucket and nothing else")
        self.assertEqual(self.box.json("events", "--unsettled", "--json"), [], "the masked skip still settles")

    def test_an_id_a_path_and_a_name_are_not_altered(self):
        """Masking is for free text: what an event is found by stays as it was sent."""
        project = os.path.join(self.box.root, "token=projects", "api_key=x")
        os.makedirs(project)
        self.box.log({"type": "capture", "tool": "Bash", "failed": "a", "fixed": "b", "call": "toolu_key=1"},
                     COMPOUND_PROJECT=project, CLAUDE_CODE_SESSION_ID="sess-secret=abc")
        event = self.box.read_events()[-1]
        self.assertEqual((event["project"], event["session"]), (project, "sess-secret=abc"))
        self.assertEqual(len(self.box.json("events", "--project", project, "--session", "sess-secret=abc", "--json")), 1)
        self.box.add("my-token-lesson", "Use when a token is needed.", "Body.\n")
        learn = self.box.read_events()[-1]
        self.assertEqual((learn["lesson"], learn["path"]), ("my-token-lesson", self.box.lesson_dir("my-token-lesson")))

    def test_a_text_is_cut_at_a_cap_and_a_long_ordinary_one_is_kept(self):
        self.box.log({"type": "error", "where": "x", "message": "m" * 3000})
        self.assertEqual(len(self.box.read_events()[-1]["message"]), 3000)
        self.box.log({"type": "error", "where": "x", "message": "m" * 100000 + GITHUB})
        message = self.box.read_events()[-1]["message"]
        self.assertEqual(len(message), 8000)
        self.assertTrue(message.endswith("…"))
        self.box.log({"type": "reuse", "lessons": ["x"] * 5000, "words": ["w" * 20000]})
        event = self.box.read_events()[-1]
        self.assertLessEqual(len(event["lessons"]), 200)
        self.assertLessEqual(len(event["words"][0]), 8000)
        self.assertLess(os.path.getsize(self.box.events), 200000)

    def test_a_secret_cut_in_two_by_the_cap_is_masked_first(self):
        """The mask is applied to the whole text and the cap to what is left."""
        self.box.log({"type": "error", "where": "x", "message": "m" * 7990 + " " + GITHUB})
        message = self.box.read_events()[-1]["message"]
        self.assertNotIn(GITHUB[:12], message)

    def test_the_masking_is_the_mods_own_rule_for_rule(self):
        """The cases of hooks/safe.test.ts, through the CLI's writer."""
        cases = [
            ("DEPLOY_TOKEN=sk-live-9f8e7d6c5b4a3210FAKE ./build.sh", "DEPLOY_TOKEN=<redacted> ./build.sh"),
            ('export AWS_SECRET_ACCESS_KEY="abc def" && make', "export AWS_SECRET_ACCESS_KEY=<redacted> && make"),
            ("BUILD_ENV=dev ./build.sh", "BUILD_ENV=dev ./build.sh"),
            ("deploy --token abc123def456 --env prod", "deploy --token <redacted> --env prod"),
            ("login --password=hunter2hunter2", "login --password=<redacted>"),
            ("curl -H 'Authorization: Bearer abcdefghijklmnop' https://x.test",
             "curl -H 'Authorization: Bearer <redacted>' https://x.test"),
            ("git clone https://jo:s3cretpw@github.com/a/b.git", "git clone https://<redacted>@github.com/a/b.git"),
            ("echo ghp_abcdefghijklmnopqrstuvwxyz0123", "echo <redacted>"),
            ("use " + "AKIA" + "ABCDEFGHIJKLMNOP" + " now", "use <redacted> now"),
            ("curl -u admin:hunter2hunter2 https://x.test/api", "curl -u <redacted> https://x.test/api"),
            ("mysql -u root -phunter2hunter2 db", "mysql -u root -p<redacted> db"),
            ("curl -H 'X-Api-Key: hunter2hunter2' https://x.test", "curl -H 'X-Api-Key: <redacted>' https://x.test"),
            ('curl -d \'{"api_key": "hunter2hunter2", "page": 2}\' https://x.test',
             'curl -d \'{"api_key": "<redacted>", "page": 2}\' https://x.test'),
            ("PROFILE=dev COUNT=3 ./build.sh", "PROFILE=dev COUNT=3 ./build.sh"),
            ("-----BEGIN RSA PRIVATE KEY-----\nMIIabc\n-----END RSA PRIVATE KEY-----\nafter", "<redacted>\nafter"),
            ("-----BEGIN OPENSSH PRIVATE KEY-----\nb3BlbnNzaC1rZXk", "<redacted>"),
        ]
        for text, _wanted in cases:
            self.box.log({"type": "guard", "lesson": "x", "text": text})
        self.assertEqual([event["text"] for event in self.box.read_events()], [wanted for _text, wanted in cases])


class MemoRedactionTest(RedactionCase):
    def test_an_earlier_request_kept_in_the_memo_is_masked(self):
        """A prompt quoted from the prompt log can hold what the user pasted."""
        self.box.add("deploy-target", "Use when deploying the release to staging.", "Pass --target staging.\n")
        found = self.box.json("find", "--request", "--json", stdin="deploy the release to staging with the target flag")
        rows = [{"id": "s1:1", "ts": "2026-09-14T10:00:00Z", "project": self.box.project, "session": "s1",
                 "prompt": "deploy it: " + call, "sessions": ["s1"]} for call in CALLS]
        proc = self.box.run("memo", stdin=json.dumps({"key": found["memo_key"], "verdict": "named",
                                                      "items": ["deploy-target", GITHUB], "prompts": rows,
                                                      "repeats": rows[:2]}))
        self.assertExit(proc, 0)
        self.box.log({"type": "nudge", "calls": 1})
        seen = self.assertNoSecret()
        self.assertIn("memo.json", seen)
        self.assertIn("<redacted>", seen["memo.json"])
        again = self.box.run("find", "--request", "--json", stdin="deploy the release to staging with the target flag")
        self.assertExit(again, 0)
        for secret in SECRETS:
            self.assertNotIn(secret, again.stdout)
        self.assertEqual(json.loads(again.stdout)["memo"]["verdict"], "named")


if __name__ == "__main__":
    unittest.main()
