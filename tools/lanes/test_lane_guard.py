import json
import os
import unittest

from lane_guard import check, glob_to_regex, overlap, same_person_open

# The same tests run in every repo that carries the lane guard, so they use their own config;
# the repo's real .github/lanes.json is only checked for shape.
CONFIG = {
    "never_merge": "^archive/",
    "side_prefix": "^side-(jay|rudd)-",
    "side_branch": "^side-(?P<person>jay|rudd)-(?P<issue>[0-9]+)-[a-z0-9][a-z0-9-]*$",
    "side_may_change": ["docs/specs/**", "docs/handoffs/jay-rudd/**", "docs/mappings/**", "app/**"],
    "side_may_not_change": ["app/api/**", "app/**/route.ts", "app/**/*.server.ts"],
}
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class RepoConfig(unittest.TestCase):
    def test_repo_lanes_json_has_every_rule_and_valid_patterns(self):
        with open(os.path.join(ROOT, ".github", "lanes.json"), encoding="utf-8") as f:
            config = json.load(f)
        for key in ("never_merge", "side_prefix", "side_branch", "side_may_change"):
            self.assertIn(key, config)
        self.assertEqual(check("m1-anything", ["x"], config), [])
        for pattern in config["side_may_change"] + config.get("side_may_not_change", []):
            glob_to_regex(pattern)

    def test_repo_examples_pass_or_are_blocked_as_listed(self):
        with open(os.path.join(ROOT, ".github", "lanes.json"), encoding="utf-8") as f:
            config = json.load(f)
        examples = config.get("examples", {})
        for path in examples.get("allowed", []):
            self.assertEqual(check("side-jay-1-example", [path], config), [], path)
        for path in examples.get("blocked", []):
            self.assertEqual(len(check("side-jay-1-example", [path], config)), 1, path)


class Globs(unittest.TestCase):
    def test_double_star_crosses_folders_single_star_does_not(self):
        self.assertTrue(glob_to_regex("docs/specs/**").match("docs/specs/m5/employee.md"))
        self.assertTrue(glob_to_regex("docs/*.md").match("docs/a.md"))
        self.assertFalse(glob_to_regex("docs/*.md").match("docs/specs/a.md"))
        self.assertFalse(glob_to_regex("docs/specs/**").match("docs/specs-old/a.md"))

    def test_double_star_slash_matches_zero_or_more_folders(self):
        rx = glob_to_regex("app/**/route.ts")
        self.assertTrue(rx.match("app/route.ts"))
        self.assertTrue(rx.match("app/api/food/route.ts"))
        self.assertFalse(rx.match("app/router.ts"))
        self.assertFalse(rx.match("lib/route.ts"))
        self.assertTrue(glob_to_regex("app/**/*.server.ts").match("app/example.server.ts"))


class Check(unittest.TestCase):
    def test_main_build_branches_are_not_limited(self):
        self.assertEqual(check("m2-bulk-window", ["sql/x.sql", "STATUS.md"], CONFIG), [])
        self.assertEqual(check("setup-multi-user-framework", [".github/workflows/x.yml"], CONFIG), [])

    def test_archive_branches_never_merge(self):
        problems = check("archive/rudd-2026-11-04-companion", ["docs/specs/a.md"], CONFIG)
        self.assertEqual(len(problems), 1)
        self.assertIn("archive branch", problems[0])

    def test_side_branch_inside_its_lane_passes(self):
        files = ["docs/specs/m5-employee-prep.md", "docs/mappings/stations.md", "docs/handoffs/jay-rudd/note.md",
                 "app/team/prep.tsx"]
        self.assertEqual(check("side-jay-14-station-list", files, CONFIG), [])

    def test_side_branch_without_issue_number_fails(self):
        problems = check("side-jay-station-list", ["docs/specs/a.md"], CONFIG)
        self.assertEqual(len(problems), 1)
        self.assertIn("issue number", problems[0])

    def test_side_agent_lanes_are_not_limited(self):
        self.assertEqual(check("side-c-ci-upkeep", [".github/workflows/example.yml"], CONFIG), [])

    def test_jay_or_rudd_prefix_with_bad_name_fails(self):
        self.assertEqual(len(check("side-rudd-count-spec", ["docs/specs/a.md"], CONFIG)), 1)

    def test_files_outside_the_lane_are_listed(self):
        problems = check("side-rudd-7-count-spec", ["docs/specs/a.md", "sql/toast/01.sql", "STATUS.md"], CONFIG)
        self.assertEqual(len(problems), 1)
        self.assertIn("`sql/toast/01.sql`", problems[0])
        self.assertIn("`STATUS.md`", problems[0])
        self.assertNotIn("docs/specs/a.md", problems[0])

    def test_excluded_paths_inside_an_allowed_folder_fail(self):
        files = ["app/team/prep.tsx", "app/api/food/route.ts", "app/x/route.ts", "app/route.ts",
                 "app/example.server.ts"]
        problems = check("side-rudd-7-screen", files, CONFIG)
        self.assertEqual(len(problems), 1)
        for f in files[1:]:
            self.assertIn(f"`{f}`", problems[0])
        self.assertNotIn("app/team/prep.tsx", problems[0])
        self.assertIn("except", problems[0])


class SamePersonOpen(unittest.TestCase):
    def test_lists_only_the_same_persons_other_branches(self):
        self.assertEqual(same_person_open("side-jay-15-roles", ["side-jay-14-stations", "side-rudd-9-x", "m2-bulk",
                                                                "side-jay-15-roles"], CONFIG),
                         ["side-jay-14-stations"])

    def test_main_build_branches_have_no_person(self):
        self.assertEqual(same_person_open("m2-bulk", ["side-jay-14-stations"], CONFIG), [])


class Overlap(unittest.TestCase):
    def test_reports_only_shared_files(self):
        others = [{"number": 4, "branch": "m2-x", "files": ["a.md", "b.md"]},
                  {"number": 5, "branch": "side-rudd-2-y", "files": ["c.md"]}]
        self.assertEqual(overlap(["b.md", "c.md", "d.md"], others),
                         [(4, "m2-x", ["b.md"]), (5, "side-rudd-2-y", ["c.md"])])

    def test_no_overlap(self):
        self.assertEqual(overlap(["a.md"], [{"number": 4, "branch": "m2-x", "files": ["b.md"]}]), [])


if __name__ == "__main__":
    unittest.main()
