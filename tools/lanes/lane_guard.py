"""Lane checks for pull requests (docs/handoffs/jay-rudd/RULES.md).

check    Fails a Jay or Rudd PR (side-jay-*, side-rudd-*) that is misnamed, changes files outside
         its lane, or is a second open PR for the same person. Main-build and side-agent
         (side-<lane>-*) branches pass.
overlap  Lists other open PRs that change the same files as this one (a warning, never a failure).

Inputs are plain files written by the workflow from `gh`, so the checks can be tested offline.
"""
import argparse
import json
import re
import sys


def glob_to_regex(pattern):
    """`**` matches across folders, `*` and `?` stay inside one folder."""
    out, i = [], 0
    while i < len(pattern):
        if pattern.startswith("**", i):
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


def check(branch, files, open_branches, config):
    """Returns a list of problems in plain English; empty means the PR may proceed."""
    if re.match(config.get("never_merge", "(?!)"), branch):
        return [f"`{branch}` is an archive branch (saved work from a retired chat, RETIRE-PROMPT.md). "
                "It is never merged; the main build takes what's needed from it."]
    if not re.match(config["side_prefix"], branch):
        return []
    m = re.match(config["side_branch"], branch)
    if not m:
        return [f"Branch `{branch}` doesn't follow the side-lane name `side-<jay|rudd>-<issue number>-<short-name>` "
                "(for example `side-jay-14-station-list`). Claim an issue on the board first and use its number."]
    problems = []
    allowed = [glob_to_regex(p) for p in config["side_may_change"]]
    blocked = [glob_to_regex(p) for p in config.get("side_may_not_change", [])]
    outside = [f for f in files
               if not any(rx.match(f) for rx in allowed) or any(rx.match(f) for rx in blocked)]
    if outside:
        listed = "\n".join(f"- `{f}`" for f in outside)
        lane = ", ".join(f"`{p}`" for p in config["side_may_change"])
        if config.get("side_may_not_change"):
            lane += ", except " + ", ".join(f"`{p}`" for p in config["side_may_not_change"])
        problems.append(f"These files are outside the side lane ({lane}); hand them to the main build "
                        f"through a spec instead:\n{listed}")
    person = m.group("person")
    others = [b for b in open_branches if b != branch and side_person(b, config) == person]
    if others:
        listed = ", ".join(f"`{b}`" for b in others)
        problems.append(f"{person.capitalize()} already has an open pull request ({listed}). "
                        "One open pull request per person: finish or close that one first.")
    return problems


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


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check")
    c.add_argument("--config", required=True)
    c.add_argument("--branch", required=True)
    c.add_argument("--files", required=True, help="file with one changed path per line")
    c.add_argument("--open-branches", required=True, help="file with the head branch of each other open PR")
    o = sub.add_parser("overlap")
    o.add_argument("--files", required=True)
    o.add_argument("--others", required=True, help='JSON file: [{"number", "branch", "files"}]')
    args = ap.parse_args(argv)

    if args.cmd == "check":
        with open(args.config, encoding="utf-8") as f:
            config = json.load(f)
        problems = check(args.branch, read_lines(args.files), read_lines(args.open_branches), config)
        if not problems:
            print(f"Lane check passed for `{args.branch}`.")
            return 0
        print(f"Lane check failed for `{args.branch}`:\n")
        print("\n\n".join(problems))
        return 1

    with open(args.others, encoding="utf-8") as f:
        others = json.load(f)
    for number, branch, shared in overlap(read_lines(args.files), others):
        print(f"- #{number} (`{branch}`): " + ", ".join(f"`{p}`" for p in shared))
    return 0


if __name__ == "__main__":
    sys.exit(main())
