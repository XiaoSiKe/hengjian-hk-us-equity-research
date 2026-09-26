#!/usr/bin/env python3
"""Check the published Skill entry and local Markdown links without network access."""

import argparse
import pathlib
import re
import sys
from urllib.parse import unquote, urlsplit


FRONTMATTER = re.compile(r"\A---\n(?P<body>.*?)\n---\n", re.DOTALL)
MARKDOWN_LINK = re.compile(r"!?\[[^\]]*\]\((?P<target>[^)]+)\)")


def check_package(root):
    root = pathlib.Path(root).resolve()
    issues = []
    skill = root / "SKILL.md"
    if not skill.is_file():
        return ["Missing root SKILL.md"], 0, 0
    match = FRONTMATTER.match(skill.read_text(encoding="utf-8"))
    if not match:
        issues.append("SKILL.md needs YAML frontmatter")
    else:
        fields = {}
        for line in match.group("body").splitlines():
            if ":" in line and not line[:1].isspace():
                key, value = line.split(":", 1)
                fields[key.strip()] = value.strip().strip('"\'')
        if fields.get("name") != root.name:
            issues.append("Skill name must match the repository directory: {}".format(root.name))
        if not fields.get("description"):
            issues.append("Skill description is missing")

    documents = list(root.rglob("*.md"))
    local_links = 0
    for document in documents:
        if ".git" in document.parts:
            continue
        for link in MARKDOWN_LINK.finditer(document.read_text(encoding="utf-8")):
            target = link.group("target").strip().strip("<>")
            if not target or target.startswith("#"):
                continue
            parsed = urlsplit(target)
            if parsed.scheme or parsed.netloc:
                continue
            local_links += 1
            path = (document.parent / unquote(parsed.path)).resolve()
            if not path.is_relative_to(root):
                issues.append("{}: link escapes package: {}".format(document.relative_to(root), target))
            elif not path.exists():
                issues.append("{}: broken local link: {}".format(document.relative_to(root), target))
    return issues, len(documents), local_links


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", default=str(pathlib.Path(__file__).resolve().parents[1]))
    args = parser.parse_args(argv)
    issues, document_count, link_count = check_package(args.root)
    if issues:
        for issue in issues:
            print(issue, file=sys.stderr)
        return 1
    print("Package OK: {} Markdown files, {} local links".format(document_count, link_count))
    return 0


if __name__ == "__main__":
    sys.exit(main())
