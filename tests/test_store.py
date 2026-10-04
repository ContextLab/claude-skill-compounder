#!/usr/bin/env python3
"""add, list, show, rm, skill: the store on disk."""

import json
import os
import stat
import time
import unittest

from test_support import NOW, Case


def read(path):
    with open(path) as handle:
        return handle.read()


class AddTest(Case):
    def test_add_writes_the_documented_format(self):
        proc = self.box.run(
            "add", "--name", "zsh-equals-word",
            "--when", 'Use when a zsh command line has a bare word starting with "=".',
            "--match", r"(^|[;&|]\s*)echo\s+=+",
            stdin="zsh expands a bare word starting with \"=\".\nQuote it.\n")
        self.assertExit(proc, 0)
        path = os.path.join(self.box.lesson_dir("zsh-equals-word"), "SKILL.md")
        self.assertEqual(read(path), (
            "---\n"
            "name: zsh-equals-word\n"
            'description: Use when a zsh command line has a bare word starting with "=".\n'
            'match: ["(^|[;&|]\\\\s*)echo\\\\s+=+"]\n'
            "created: 2026-09-21\n"
            "origin: project project, session sess-000\n"
            "---\n"
            "zsh expands a bare word starting with \"=\".\n"
            "Quote it.\n"))
        self.assertIn(self.box.lesson_dir("zsh-equals-word"), proc.stdout)

    def test_add_logs_a_learn_event_with_the_documented_fields(self):
        self.box.add("first-lesson")
        events = self.box.read_events()
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0], {
            "ts": "2026-09-21T14:13:20Z", "type": "learn", "session": "sess-0001-aaaa",
            "project": self.box.project, "lesson": "first-lesson", "level": "project",
            "kind": "lesson", "path": self.box.lesson_dir("first-lesson"),
            "guard": False, "update": False})

    def test_level_defaults_to_project_and_user_is_honoured(self):
        self.box.add("at-project")
        self.box.add("at-user", "Use when.", "Body.\n", "--level", "user")
        self.assertTrue(os.path.isfile(os.path.join(self.box.lesson_dir("at-project"), "SKILL.md")))
        self.assertTrue(os.path.isfile(os.path.join(self.box.lesson_dir("at-user", "user"), "SKILL.md")))

    def test_origin_flag_is_written(self):
        self.box.add("with-origin", "Use when.", "Body.\n", "--origin", "a   hand\nwritten origin")
        self.assertIn("origin: a hand written origin\n",
                      read(os.path.join(self.box.lesson_dir("with-origin"), "SKILL.md")))

    def test_json_output(self):
        proc = self.box.run("add", "--name", "as-json", "--when", "Use when.", "--json", stdin="Body.\n")
        self.assertExit(proc, 0)
        self.assertEqual(json.loads(proc.stdout), {
            "name": "as-json", "level": "project", "kind": "lesson",
            "path": self.box.lesson_dir("as-json"), "updated": False, "guard": False})

    def test_attach_copies_the_file_and_keeps_its_executable_bit(self):
        source = os.path.join(self.box.root, "fix.sh")
        with open(source, "w") as handle:
            handle.write("#!/bin/sh\necho fixed\n")
        os.chmod(source, 0o755)
        self.box.add("with-script", "Use when.", "Run fix.sh.\n", "--attach", source)
        copied = os.path.join(self.box.lesson_dir("with-script"), "fix.sh")
        self.assertEqual(read(copied), "#!/bin/sh\necho fixed\n")
        self.assertTrue(os.stat(copied).st_mode & stat.S_IXUSR)
        self.assertEqual(sorted(os.listdir(self.box.lesson_dir("with-script"))), ["SKILL.md", "fix.sh"])

    def test_no_temporary_files_are_left_behind(self):
        self.box.add("tidy-lesson")
        lessons = os.path.dirname(self.box.lesson_dir("tidy-lesson"))
        self.assertEqual(os.listdir(lessons), ["tidy-lesson"])
        self.assertEqual(os.listdir(self.box.lesson_dir("tidy-lesson")), ["SKILL.md"])


class AddRefusalTest(Case):
    def refused(self, *args, **kw):
        before = self.box.snapshot()
        proc = self.box.run(*args, **kw)
        self.assertExit(proc, 2)
        self.assertTrue(proc.stderr.startswith("compound: ") or "usage" in proc.stderr, proc.stderr)
        self.assertEqual(self.box.snapshot(), before, "a refused add wrote something")
        return proc.stderr

    def test_bad_slugs(self):
        for name in ("A", "Has-Upper", "-leading", "x", "has space", "under_score", "a" * 64, ""):
            err = self.refused("add", "--name=" + name, "--when", "Use when.", stdin="Body.\n")
            self.assertIn("slug", err)

    def test_longest_and_shortest_slugs_are_accepted(self):
        self.box.add("ab")
        self.box.add("a" * 63)

    def test_empty_description(self):
        err = self.refused("add", "--name", "no-when", "--when", "   ", stdin="Body.\n")
        self.assertIn("--when", err)

    def test_missing_description(self):
        err = self.refused("add", "--name", "no-when", stdin="Body.\n")
        self.assertIn("--when", err)

    def test_empty_body(self):
        err = self.refused("add", "--name", "no-body", "--when", "Use when.", stdin="  \n\n")
        self.assertIn("body is empty", err)

    def test_match_that_does_not_compile(self):
        err = self.refused("add", "--name", "bad-re", "--when", "Use when.", "--match", "echo (", stdin="Body.\n")
        self.assertIn("does not compile", err)

    def test_match_that_matches_the_empty_string(self):
        for pattern in ("", "a*", "(echo)?", "^", ".*"):
            err = self.refused("add", "--name", "empty-re", "--when", "Use when.",
                               "--match", pattern, stdin="Body.\n")
            self.assertIn("empty string", err)

    def test_one_bad_match_among_good_ones_refuses_the_lot(self):
        err = self.refused("add", "--name", "mixed-re", "--when", "Use when.",
                           "--match", "echo =", "--match", "x*", stdin="Body.\n")
        self.assertIn("'x*'", err)

    def test_level_general_is_refused(self):
        err = self.refused("add", "--name", "to-general", "--when", "Use when.",
                           "--level", "general", stdin="Body.\n")
        self.assertIn("promote", err)

    def test_unknown_level_is_refused(self):
        self.refused("add", "--name", "to-nowhere", "--when", "Use when.", "--level", "team", stdin="Body.\n")

    def test_a_name_that_exists_is_refused_at_any_level(self):
        self.box.add("taken-name", "Use when.", "Body.\n", "--level", "user")
        err = self.refused("add", "--name", "taken-name", "--when", "Use when.", stdin="Other body.\n")
        self.assertIn("already exists at the user level", err)
        self.assertFalse(os.path.exists(self.box.lesson_dir("taken-name")))

    def test_a_name_held_by_a_general_lesson_is_refused(self):
        self.box.write_lesson(self.box.lesson_dir("shipped", "general"), "shipped")
        err = self.refused("add", "--name", "shipped", "--when", "Use when.", stdin="Body.\n")
        self.assertIn("general", err)

    def test_a_name_held_by_a_skill_is_refused(self):
        self.box.write_lesson(self.box.skill_dir("a-skill", "user"), "a-skill")
        err = self.refused("add", "--name", "a-skill", "--when", "Use when.", stdin="Body.\n")
        self.assertIn("already exists", err)

    def test_attach_that_is_not_a_file(self):
        err = self.refused("add", "--name", "no-file", "--when", "Use when.",
                           "--attach", os.path.join(self.box.root, "absent.sh"), stdin="Body.\n")
        self.assertIn("is not a file", err)

    def test_attach_named_skill_md(self):
        source = os.path.join(self.box.root, "SKILL.md")
        with open(source, "w") as handle:
            handle.write("x")
        err = self.refused("add", "--name", "clobber", "--when", "Use when.", "--attach", source, stdin="Body.\n")
        self.assertIn("SKILL.md", err)

    def test_update_of_a_name_that_does_not_exist(self):
        err = self.refused("add", "--name", "not-there", "--when", "Use when.", "--update", stdin="Body.\n")
        self.assertIn("no lesson named", err)

    def test_update_of_a_general_lesson(self):
        self.box.write_lesson(self.box.lesson_dir("shipped", "general"), "shipped")
        err = self.refused("add", "--name", "shipped", "--when", "Use when.", "--update", stdin="Body.\n")
        self.assertIn("general pool", err)

    def test_match_and_no_match_together(self):
        self.box.add("a-guard", "Use when.", "Body.\n", "--match", "rm -rf")
        err = self.refused("add", "--name", "a-guard", "--update", "--match", "x", "--no-match", stdin="")
        self.assertIn("--no-match", err)


class UpdateTest(Case):
    def test_update_rewrites_the_lesson_where_it_is(self):
        self.box.add("moves-not", "Use when old.", "Old body.\n", "--level", "user", "--match", "old-cmd")
        proc = self.box.run("add", "--name", "moves-not", "--when", "Use when new.", "--update",
                            stdin="New body.\n", COMPOUND_NOW=NOW + 86400 * 3)
        self.assertExit(proc, 0)
        self.assertFalse(os.path.exists(self.box.lesson_dir("moves-not")),
                         "--update must not create a project copy")
        self.assertEqual(read(os.path.join(self.box.lesson_dir("moves-not", "user"), "SKILL.md")), (
            "---\n"
            "name: moves-not\n"
            "description: Use when new.\n"
            'match: ["old-cmd"]\n'
            "created: 2026-09-21\n"
            "origin: project project, session sess-000\n"
            "updated: 2026-09-24\n"
            "---\n"
            "New body.\n"))
        learn = self.box.read_events()[-1]
        self.assertEqual((learn["type"], learn["lesson"], learn["level"], learn["update"], learn["guard"]),
                         ("learn", "moves-not", "user", True, True))

    def test_update_keeps_what_is_not_given(self):
        self.box.add("keeps", "Use when kept.", "Kept body.\n")
        proc = self.box.run("add", "--name", "keeps", "--update", "--match", "danger\\s+cmd", stdin="")
        self.assertExit(proc, 0)
        text = read(os.path.join(self.box.lesson_dir("keeps"), "SKILL.md"))
        self.assertIn("description: Use when kept.\n", text)
        self.assertIn('match: ["danger\\\\s+cmd"]\n', text)
        self.assertTrue(text.endswith("---\nKept body.\n"))

    def test_no_match_drops_the_guard(self):
        self.box.add("was-guard", "Use when.", "Body.\n", "--match", "danger")
        self.assertExit(self.box.run("add", "--name", "was-guard", "--update", "--no-match", stdin=""), 0)
        self.assertNotIn("match:", read(os.path.join(self.box.lesson_dir("was-guard"), "SKILL.md")))
        self.assertEqual(self.box.json("list", "--json")[0]["match"], [])

    def test_update_refuses_a_bad_match_and_leaves_the_lesson(self):
        self.box.add("stays", "Use when.", "Body.\n")
        before = read(os.path.join(self.box.lesson_dir("stays"), "SKILL.md"))
        proc = self.box.run("add", "--name", "stays", "--update", "--match", "(", stdin="")
        self.assertExit(proc, 2)
        self.assertEqual(read(os.path.join(self.box.lesson_dir("stays"), "SKILL.md")), before)

    def test_update_attaches_a_script(self):
        self.box.add("gets-script")
        source = os.path.join(self.box.root, "repair.py")
        with open(source, "w") as handle:
            handle.write("print('repaired')\n")
        self.assertExit(self.box.run("add", "--name", "gets-script", "--update", "--attach", source, stdin=""), 0)
        self.assertEqual(read(os.path.join(self.box.lesson_dir("gets-script"), "repair.py")), "print('repaired')\n")

    def test_update_of_a_skill_keeps_its_other_frontmatter(self):
        directory = self.box.skill_dir("routable", "user")
        self.box.write_lesson(directory, "routable", extra="allowed-tools: Bash\n")
        self.assertExit(self.box.run("add", "--name", "routable", "--update", "--when", "Use when routed.",
                                     stdin="Step one.\n"), 0)
        text = read(os.path.join(directory, "SKILL.md"))
        self.assertIn("allowed-tools: Bash\n", text)
        self.assertIn("description: Use when routed.\n", text)
        self.assertTrue(text.endswith("---\nStep one.\n"))


class ListTest(Case):
    def test_list_json_carries_every_documented_field(self):
        self.box.add("guarded", "Use when guarded.", "Body.\n", "--match", "danger")
        rows = self.box.json("list", "--json")
        self.assertEqual(rows, [{
            "level": "project", "kind": "lesson", "name": "guarded",
            "description": "Use when guarded.", "path": self.box.lesson_dir("guarded"),
            "match": ["danger"], "counts": {"reuse": 0, "guard": 0, "recall": 0, "learn": 1},
            "ineffective": False}])

    def test_all_three_levels_and_both_kinds_are_listed(self):
        self.box.add("p-lesson")
        self.box.add("u-lesson", "Use when.", "Body.\n", "--level", "user")
        self.box.write_lesson(self.box.lesson_dir("g-lesson", "general"), "g-lesson")
        self.box.write_lesson(self.box.skill_dir("p-skill", "project"), "p-skill")
        self.box.write_lesson(self.box.skill_dir("u-skill", "user"), "u-skill")
        self.box.write_lesson(self.box.skill_dir("g-skill", "general"), "g-skill")
        rows = self.box.json("list", "--json")
        self.assertEqual([(row["level"], row["kind"], row["name"]) for row in rows], [
            ("project", "lesson", "p-lesson"), ("project", "skill", "p-skill"),
            ("user", "lesson", "u-lesson"), ("user", "skill", "u-skill"),
            ("general", "lesson", "g-lesson"), ("general", "skill", "g-skill")])

    def test_level_filter(self):
        self.box.add("p-lesson")
        self.box.add("u-lesson", "Use when.", "Body.\n", "--level", "user")
        self.assertEqual([row["name"] for row in self.box.json("list", "--json", "--level", "user")], ["u-lesson"])
        self.assertEqual([row["name"] for row in self.box.json("list", "--json", "--level", "general")], [])

    def test_a_skill_reached_through_a_symlink_is_listed_once(self):
        real = os.path.join(self.box.root, "elsewhere", "linked-skill")
        self.box.write_lesson(real, "linked-skill", description="Use when linked.")
        os.makedirs(os.path.join(self.box.claude, "skills"))
        os.symlink(real, self.box.skill_dir("linked-skill", "user"))
        rows = self.box.json("list", "--json")
        self.assertEqual([(row["level"], row["kind"], row["name"], row["description"]) for row in rows],
                         [("user", "skill", "linked-skill", "Use when linked.")])

    def test_a_user_skill_that_links_into_the_package_is_general_and_listed_once(self):
        self.box.write_lesson(self.box.skill_dir("shipped-skill", "general"), "shipped-skill")
        os.makedirs(os.path.join(self.box.claude, "skills"))
        os.symlink(self.box.skill_dir("shipped-skill", "general"), self.box.skill_dir("shipped-skill", "user"))
        rows = self.box.json("list", "--json")
        self.assertEqual([(row["level"], row["name"]) for row in rows], [("general", "shipped-skill")])

    def test_a_skill_with_yaml_style_frontmatter_is_read(self):
        directory = self.box.skill_dir("foreign", "user")
        os.makedirs(directory)
        with open(os.path.join(directory, "SKILL.md"), "w") as handle:
            handle.write('---\nname: foreign\ndescription: >\n  Use when the description\n  is folded.\n'
                         'license: "MIT"\n---\nBody.\n')
        rows = self.box.json("list", "--json")
        self.assertEqual(rows[0]["description"], "Use when the description is folded.")

    def test_scripts_are_added_on_request(self):
        project = self.box.project
        os.makedirs(os.path.join(project, "scripts", "sub", "deeper"))
        os.makedirs(os.path.join(project, "bin"))
        os.makedirs(os.path.join(project, "tools"))
        os.makedirs(os.path.join(project, "src"))
        files = {
            "scripts/release.sh": "#!/bin/sh\n# Cut a release and tag it.\necho\n",
            "scripts/sub/nested.py": '"""Nested helper docstring."""\n',
            "scripts/sub/deeper/too-deep.sh": "# too deep\n",
            "scripts/notes.txt": "not a script\n",
            "bin/runme": "#!/bin/sh\n#\n# Runs the thing.\n",
            "tools/gen.py": "#!/usr/bin/env python3\n# -*- coding: utf-8 -*-\n# Generate fixtures.\n",
            "src/main.py": "# not under a scripts directory\n",
        }
        for rel, text in files.items():
            with open(os.path.join(project, rel), "w") as handle:
                handle.write(text)
        os.chmod(os.path.join(project, "bin", "runme"), 0o755)
        without = self.box.json("list", "--json")
        self.assertEqual(without, [])
        rows = self.box.json("list", "--json", "--scripts")
        self.assertEqual([(row["kind"], row["level"], row["name"], row["description"]) for row in rows], [
            ("script", "project", "scripts/release.sh", "Cut a release and tag it."),
            ("script", "project", "scripts/sub/nested.py", "Nested helper docstring."),
            ("script", "project", "bin/runme", "Runs the thing."),
            ("script", "project", "tools/gen.py", "Generate fixtures."),
        ])
        self.assertEqual(rows[0]["path"], os.path.join(project, "scripts", "release.sh"))
        self.assertEqual(rows[0]["match"], [])
        self.assertEqual(rows[0]["counts"], {"reuse": 0, "guard": 0, "recall": 0, "learn": 0})

    def test_scripts_are_capped_at_two_hundred(self):
        os.makedirs(os.path.join(self.box.project, "scripts"))
        for index in range(230):
            with open(os.path.join(self.box.project, "scripts", "s%03d.sh" % index), "w") as handle:
                handle.write("# script %d\n" % index)
        self.assertEqual(len(self.box.json("list", "--json", "--scripts")), 200)

    def test_human_output_names_each_lesson(self):
        self.box.add("readable", "Use when read by a person.", "Body.\n", "--match", "danger")
        proc = self.box.run("list")
        self.assertExit(proc, 0)
        self.assertIn("readable", proc.stdout)
        self.assertIn("guard", proc.stdout)
        self.assertIn("Use when read by a person.", proc.stdout)

    def test_an_empty_store_lists_nothing(self):
        proc = self.box.run("list")
        self.assertExit(proc, 0)
        self.assertIn("nothing recorded", proc.stdout)

    def test_the_project_is_the_git_top_level_without_the_override(self):
        from test_support import git_ok
        repo = os.path.join(self.box.root, "repo")
        os.makedirs(os.path.join(repo, "deep", "inside"))
        git_ok("init", "-q", repo)
        proc = self.box.run("add", "--name", "in-repo", "--when", "Use when.", stdin="Body.\n",
                            cwd=os.path.join(repo, "deep", "inside"), COMPOUND_PROJECT=None)
        self.assertExit(proc, 0)
        self.assertTrue(os.path.isfile(os.path.join(repo, ".claude", "compound", "lessons", "in-repo", "SKILL.md")))

    def test_outside_a_repository_the_project_is_the_working_directory(self):
        plain = os.path.join(self.box.root, "plain")
        os.makedirs(plain)
        proc = self.box.run("add", "--name", "in-plain", "--when", "Use when.", stdin="Body.\n",
                            cwd=plain, COMPOUND_PROJECT=None)
        self.assertExit(proc, 0)
        self.assertTrue(os.path.isfile(os.path.join(plain, ".claude", "compound", "lessons", "in-plain", "SKILL.md")))


class ShowTest(Case):
    def test_show_prints_path_and_text(self):
        self.box.add("shown", "Use when shown.", "The shown body.\n")
        proc = self.box.run("show", "shown")
        self.assertExit(proc, 0)
        self.assertIn(self.box.lesson_dir("shown"), proc.stdout)
        self.assertIn("description: Use when shown.", proc.stdout)
        self.assertIn("The shown body.", proc.stdout)

    def test_show_json(self):
        source = os.path.join(self.box.root, "helper.sh")
        with open(source, "w") as handle:
            handle.write("# helper\n")
        self.box.add("shown", "Use when shown.", "The shown body.\n", "--attach", source)
        row = self.box.json("show", "shown", "--json")
        self.assertEqual(row["path"], self.box.lesson_dir("shown"))
        self.assertEqual(row["text"], read(os.path.join(self.box.lesson_dir("shown"), "SKILL.md")))
        self.assertEqual(row["files"], ["helper.sh"])
        self.assertEqual(row["level"], "project")

    def test_show_of_an_unknown_name(self):
        proc = self.box.run("show", "nothing-here")
        self.assertExit(proc, 2)
        self.assertIn("no lesson or skill named", proc.stderr)


class RmTest(Case):
    def test_rm_removes_the_lesson_directory(self):
        self.box.add("doomed")
        proc = self.box.run("rm", "doomed")
        self.assertExit(proc, 0)
        self.assertFalse(os.path.exists(self.box.lesson_dir("doomed")))
        self.assertEqual(self.box.json("list", "--json"), [])

    def test_rm_of_an_unknown_name(self):
        self.assertExit(self.box.run("rm", "nothing-here"), 2)

    def test_rm_refuses_a_skill_without_force(self):
        directory = self.box.skill_dir("users-own", "user")
        self.box.write_lesson(directory, "users-own")
        proc = self.box.run("rm", "users-own")
        self.assertExit(proc, 2)
        self.assertTrue(os.path.isdir(directory))
        self.assertExit(self.box.run("rm", "users-own", "--force"), 0)
        self.assertFalse(os.path.exists(directory))

    def test_rm_force_on_a_linked_skill_removes_the_link_only(self):
        real = os.path.join(self.box.root, "elsewhere", "linked")
        self.box.write_lesson(real, "linked")
        os.makedirs(os.path.join(self.box.claude, "skills"))
        os.symlink(real, self.box.skill_dir("linked", "user"))
        self.assertExit(self.box.run("rm", "linked", "--force"), 0)
        self.assertFalse(os.path.lexists(self.box.skill_dir("linked", "user")))
        self.assertTrue(os.path.isfile(os.path.join(real, "SKILL.md")))

    def test_rm_refuses_the_general_pool(self):
        directory = self.box.lesson_dir("shipped", "general")
        self.box.write_lesson(directory, "shipped")
        proc = self.box.run("rm", "shipped")
        self.assertExit(proc, 2)
        self.assertTrue(os.path.isdir(directory))


class SkillTest(Case):
    def test_skill_moves_the_directory_to_the_skills_directory_of_its_level(self):
        source = os.path.join(self.box.root, "helper.sh")
        with open(source, "w") as handle:
            handle.write("# helper\n")
        self.box.add("becomes-skill", "Use when.", "Step one.\n", "--attach", source)
        text = read(os.path.join(self.box.lesson_dir("becomes-skill"), "SKILL.md"))
        proc = self.box.run("skill", "becomes-skill")
        self.assertExit(proc, 0)
        self.assertFalse(os.path.exists(self.box.lesson_dir("becomes-skill")))
        target = self.box.skill_dir("becomes-skill", "project")
        self.assertEqual(read(os.path.join(target, "SKILL.md")), text)
        self.assertTrue(os.path.isfile(os.path.join(target, "helper.sh")))
        rows = self.box.json("list", "--json")
        self.assertEqual([(row["level"], row["kind"], row["name"], row["path"]) for row in rows],
                         [("project", "skill", "becomes-skill", target)])

    def test_a_user_lesson_becomes_a_user_skill(self):
        self.box.add("user-skill", "Use when.", "Body.\n", "--level", "user")
        self.assertExit(self.box.run("skill", "user-skill"), 0)
        self.assertTrue(os.path.isfile(os.path.join(self.box.skill_dir("user-skill", "user"), "SKILL.md")))

    def test_skill_twice_is_refused(self):
        self.box.add("once-only")
        self.assertExit(self.box.run("skill", "once-only"), 0)
        proc = self.box.run("skill", "once-only")
        self.assertExit(proc, 2)
        self.assertIn("already a skill", proc.stderr)

    def test_skill_of_an_unknown_name(self):
        self.assertExit(self.box.run("skill", "nothing-here"), 2)

    def test_skill_refuses_an_occupied_target(self):
        self.box.add("blocked")
        os.makedirs(self.box.skill_dir("blocked", "project"))
        proc = self.box.run("skill", "blocked")
        self.assertExit(proc, 2)
        self.assertTrue(os.path.isfile(os.path.join(self.box.lesson_dir("blocked"), "SKILL.md")))

    def test_skill_refuses_the_general_pool(self):
        self.box.write_lesson(self.box.lesson_dir("shipped", "general"), "shipped")
        self.assertExit(self.box.run("skill", "shipped"), 2)
        self.assertTrue(os.path.isdir(self.box.lesson_dir("shipped", "general")))

    def test_counts_follow_the_name_across_the_move(self):
        self.box.add("counted")
        self.box.log({"type": "reuse", "lessons": ["counted"]})
        self.assertExit(self.box.run("skill", "counted"), 0)
        self.assertEqual(self.box.json("list", "--json")[0]["counts"]["reuse"], 1)


class ClockTest(Case):
    def test_without_a_pinned_clock_the_real_time_is_used(self):
        before = int(time.time())
        proc = self.box.run("add", "--name", "real-time", "--when", "Use when.", stdin="Body.\n", COMPOUND_NOW=None)
        self.assertExit(proc, 0)
        stamp = self.box.read_events()[0]["ts"]
        import calendar
        logged = calendar.timegm(time.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ"))
        self.assertTrue(before - 1 <= logged <= int(time.time()) + 1, stamp)

    def test_an_iso_pinned_clock(self):
        self.box.add("iso-time", COMPOUND_NOW="2026-01-02T03:04:05Z")
        self.assertEqual(self.box.read_events()[0]["ts"], "2026-01-02T03:04:05Z")
        self.assertIn("created: 2026-01-02\n", read(os.path.join(self.box.lesson_dir("iso-time"), "SKILL.md")))


if __name__ == "__main__":
    unittest.main()
