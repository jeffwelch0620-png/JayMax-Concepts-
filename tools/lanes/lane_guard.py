"""Lane checks for pull requests (jmax-workspace docs/handoffs/jay-rudd/RULES.md).

check    Fails a Jay or Rudd PR (side-jay-*, side-rudd-*) that is misnamed or changes files outside
         its lane, and any PR from an archive/* branch. Depends only on the PR itself, so the
         result never goes stale. Main-build and side-agent (side-<lane>-*) branches pass.
overlap  Lists other open PRs that change the same files as this one, and warns when the same
         person already has another open PR (a warning, never a failure).

Inputs are plain files written by the workflow from `gh`, so the checks can be tested offline.
"""
import argparse
import json
import re
import sys


def glob_to_regex(pattern):
    """`**/` matches zero or more folders, a trailing `**` anything below; `*` and `?` stay in one folder."""
    out, i = [], 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
        elif pattern.startswith("**", i):
            out.append(".*")
            i += 2
        elif pattern[i] == "*":
            out.append("[^/]*")
            i += 1
        elif pattern[i] == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(pattern[i]))
            i += 1
    return re.compile("^" + "".join(out) + "$")


def side_person(branch, config):
    m = re.match(config["side_branch"], branch)
    return m.group("person") if m else None


def check(branch, files, config):
    """Returns a list of problems in plain English; empty means the PR may proceed."""
    if re.match(config.get("never_merge", "(?!)"), branch):
        return [f"`{branch}` is an archive branch (saved work from a retired chat, RETIRE-PROMPT.md). "
                "It is never merged; the main build takes what's needed from it."]
    if not re.match(config["side_prefix"], branch):
        return []
    if not re.match(config["side_branch"], branch):
        return [f"Branch `{branch}` doesn't follow the side-lane name `side-<jay|rudd>-<issue number>-<short-name>` "
                "(for example `side-jay-14-station-list`). Claim an issue on the board first and use its number."]
    allowed = [glob_to_regex(p) for p in config["side_may_change"]]
    blocked = [glob_to_regex(p) for p in config.get("side_may_not_change", [])]
    outside = [f for f in files
               if not any(rx.match(f) for rx in allowed) or any(rx.match(f) for rx in blocked)]
    if not outside:
        return []
    listed = "\n".join(f"- `{f}`" for f in outside)
    lane = ", ".join(f"`{p}`" for p in config["side_may_change"])
    if config.get("side_may_not_change"):
        lane += ", except " + ", ".join(f"`{p}`" for p in config["side_may_not_change"])
    return [f"These files are outside the side lane ({lane}); hand them to the main build "
            f"through a spec instead:\n{listed}"]


def same_person_open(branch, open_branches, config):
    """Other open side-lane branches of the same person (one open pull request per person)."""
    person = side_person(branch, config)
    if not person:
        return []
    return [b for b in open_branches if b != branch and side_person(b, config) == person]


def overlap(files, others):
    """others: [{"number", "branch", "files"}] for the other open PRs. Returns [(number, branch, shared files)]."""
    mine = set(files)
    hits = []
    for pr in others:
        shared = sorted(mine & set(pr["files"]))
        if shared:
            hits.append((pr["number"], pr["branch"], shared))
    return hits


def read_lines(path):
    with open(path, encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check")
    c.add_argument("--config", required=True)
    c.add_argument("--branch", required=True)
    c.add_argument("--files", required=True, help="file with one changed path per line")
    o = sub.add_parser("overlap")
    o.add_argument("--config", required=True)
    o.add_argument("--branch", required=True)
    o.add_argument("--files", required=True)
    o.add_argument("--others", required=True, help='JSON file: [{"number", "branch", "files"}]')
    args = ap.parse_args(argv)
    config = load(args.config)

    if args.cmd == "check":
        problems = check(args.branch, read_lines(args.files), config)
        if not problems:
            print(f"Lane check passed for `{args.branch}`.")
            return 0
        print(f"Lane check failed for `{args.branch}`:\n")
        print("\n\n".join(problems))
        return 1

    others = load(args.others)
    mine = same_person_open(args.branch, [pr["branch"] for pr in others], config)
    if mine:
        numbers = ", ".join(f"#{pr['number']} (`{pr['branch']}`)" for pr in others if pr["branch"] in mine)
        print(f"- **One open pull request per person:** {side_person(args.branch, config)} also has {numbers} open. "
              "Finish or close that one first.")
    for number, branch, shared in overlap(read_lines(args.files), others):
        print(f"- **Same files as #{number}** (`{branch}`): " + ", ".join(f"`{p}`" for p in shared))
    return 0


if __name__ == "__main__":
    sys.exit(main())
