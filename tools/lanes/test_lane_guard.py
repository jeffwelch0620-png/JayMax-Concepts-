import json
import os
import unittest

from lane_guard import check, glob_to_regex, overlap

# The same tests run in every repo that carries the lane guard, so they use their own config;
# the repo's real .github/lanes.json is only checked for shape.
CONFIG = {
    "never_merge": "^archive/",
    "side_prefix": "^side-(jay|rudd)-",
    "side_branch": "^side-(?P<person>jay|rudd)-(?P<issue>[0-9]+)-[a-z0-9][a-z0-9-]*$",
    "side_may_change": ["docs/specs/**", "docs/handoffs/jay-rudd/**", "docs/mappings/**", "app/**"],
    "side_may_not_change": ["app/api/**", "app/**/route.ts"],
}
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class RepoConfig(unittest.TestCase):
    def test_repo_lanes_json_has_every_rule_and_valid_patterns(self):
        with open(os.path.join(ROOT, ".github", "lanes.json"), encoding="utf-8") as f:
            config = json.load(f)
        for key in ("never_merge", "side_prefix", "side_branch", "side_may_change"):
            self.assertIn(key, config)
        self.assertEqual(check("m1-anything", ["x"], [], config), [])
        for pattern in config["side_may_change"] + config.get("side_may_not_change", []):
            glob_to_regex(pattern)


class Globs(unittest.TestCase):
    def test_double_star_crosses_folders_single_star_does_not(self):
        self.assertTrue(glob_to_regex("docs/specs/**").match("docs/specs/m5/employee.md"))
        self.assertTrue(glob_to_regex("docs/*.md").match("docs/a.md"))
        self.assertFalse(glob_to_regex("docs/*.md").match("docs/specs/a.md"))
        self.assertFalse(glob_to_regex("docs/specs/**").match("docs/specs-old/a.md"))


class Check(unittest.TestCase):
    def test_main_build_branches_are_not_limited(self):
        self.assertEqual(check("m2-bulk-window", ["sql/x.sql", "STATUS.md"], [], CONFIG), [])
        self.assertEqual(check("setup-multi-user-framework", [".github/workflows/x.yml"], [], CONFIG), [])

    def test_archive_branches_never_merge(self):
        problems = check("archive/rudd-2026-11-04-companion", ["docs/specs/a.md"], [], CONFIG)
        self.assertEqual(len(problems), 1)
        self.assertIn("archive branch", problems[0])

    def test_side_branch_inside_its_lane_passes(self):
        files = ["docs/specs/m5-employee-prep.md", "docs/mappings/stations.md", "docs/handoffs/jay-rudd/note.md",
                 "app/team/prep.tsx"]
        self.assertEqual(check("side-jay-14-station-list", files, [], CONFIG), [])

    def test_side_branch_without_issue_number_fails(self):
        problems = check("side-jay-station-list", ["docs/specs/a.md"], [], CONFIG)
        self.assertEqual(len(problems), 1)
        self.assertIn("issue number", problems[0])

    def test_side_agent_lanes_are_not_limited(self):
        self.assertEqual(check("side-c-ci-upkeep", [".github/workflows/example.yml"], [], CONFIG), [])

    def test_jay_or_rudd_prefix_with_bad_name_fails(self):
        self.assertEqual(len(check("side-rudd-count-spec", ["docs/specs/a.md"], [], CONFIG)), 1)

    def test_files_outside_the_lane_are_listed(self):
        problems = check("side-rudd-7-count-spec", ["docs/specs/a.md", "sql/toast/01.sql", "STATUS.md"], [], CONFIG)
        self.assertEqual(len(problems), 1)
        self.assertIn("`sql/toast/01.sql`", problems[0])
        self.assertIn("`STATUS.md`", problems[0])
        self.assertNotIn("docs/specs/a.md", problems[0])

    def test_excluded_paths_inside_an_allowed_folder_fail(self):
        problems = check("side-rudd-7-screen", ["app/team/prep.tsx", "app/api/food/route.ts", "app/x/route.ts"],
                         [], CONFIG)
        self.assertEqual(len(problems), 1)
        self.assertIn("`app/api/food/route.ts`", problems[0])
        self.assertIn("`app/x/route.ts`", problems[0])
        self.assertNotIn("app/team/prep.tsx", problems[0])
        self.assertIn("except", problems[0])

    def test_second_open_pr_for_the_same_person_fails(self):
        problems = check("side-jay-15-roles", ["docs/specs/a.md"], ["side-jay-14-stations", "side-rudd-9-x"], CONFIG)
        self.assertEqual(len(problems), 1)
        self.assertIn("side-jay-14-stations", problems[0])

    def test_other_persons_open_pr_is_fine(self):
        self.assertEqual(check("side-jay-15-roles", ["docs/specs/a.md"], ["side-rudd-9-x", "m2-bulk"], CONFIG), [])

    def test_own_branch_in_open_list_is_not_counted(self):
        self.assertEqual(check("side-jay-15-roles", ["docs/specs/a.md"], ["side-jay-15-roles"], CONFIG), [])


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
