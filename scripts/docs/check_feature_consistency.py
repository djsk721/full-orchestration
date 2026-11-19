"""Check documented feature status and flag code changes that merit a docs review."""

import argparse
import json
import re
import subprocess

from check_doc_structure import DOCS, LANGUAGES, ROOT, finish, pages

MANIFEST = DOCS / "internal/features.json"
STATUSES = {"IMPLEMENTED", "PARTIALLY_IMPLEMENTED", "PLANNED", "NOT_VERIFIED"}
MARKER = re.compile(r"^<!-- feature: ([a-z0-9-]+) ([A-Z_]+) -->$", re.MULTILINE)


def check(features):
    errors = []
    observed = {}
    for locale in LANGUAGES:
        for relative in sorted(pages(locale)):
            doc = DOCS / locale / relative
            source = doc.read_text(encoding="utf-8")
            matches = MARKER.findall(source)
            if len(matches) != len(re.findall(r"^<!-- feature:", source, re.MULTILINE)):
                errors.append(f"{doc.relative_to(ROOT)}: malformed feature marker")
            for feature, status in matches:
                observed.setdefault((locale, relative, feature), []).append(status)

    for feature, details in features.items():
        status = details["status"]
        primary = details["primary"]
        if status not in STATUSES:
            errors.append(f"{feature}: unsupported feature status {status}")
        if status == "PLANNED" and primary != "roadmap.md":
            errors.append(f"{feature}: planned features must be declared in the roadmap")
        if status in {"IMPLEMENTED", "PARTIALLY_IMPLEMENTED"} and not details["evidence"]:
            errors.append(f"{feature}: implemented behavior needs source evidence")
        for locale in LANGUAGES:
            seen = observed.pop((locale, primary, feature), [])
            if seen != [status]:
                errors.append(f"docs/{locale}/{primary}: expected one marker for {feature} {status}, got {seen}")
            for related in details["related"]:
                if not (DOCS / locale / related).is_file():
                    errors.append(f"docs/{locale}/{related}: mapped page for {feature} is missing")
        for file, symbols in (details["evidence"] | details["tests"]).items():
            path = ROOT / file
            if not path.is_file():
                errors.append(f"{file}: evidence for {feature} missing")
                continue
            source = path.read_text(encoding="utf-8")
            for symbol in symbols:
                if not re.search(r"(?<![\w])" + re.escape(symbol) + r"(?!\w)", source):
                    errors.append(f"{file}: {feature} evidence '{symbol}' missing")

    for locale, path, feature in sorted(observed):
        errors.append(f"docs/{locale}/{path}: unexpected feature marker for {feature}")
    return errors


def review_changes(features, base):
    output = subprocess.check_output(
        ["git", "diff", "--name-only", "-z", base + "...HEAD", "--"], cwd=ROOT,
    ).decode()
    changed = set(output.rstrip("\0").split("\0"))
    for feature, details in features.items():
        touched = changed & details["evidence"].keys()
        mapped = {f"docs/{lang}/{page}" for lang in LANGUAGES for page in [details["primary"], *details["related"]]}
        if touched and not changed & mapped:
            print(f"Review {feature}: {', '.join(sorted(touched))} changed. Check {details['primary']} if behavior changed.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", help="base commit for advisory documentation review")
    args = parser.parse_args()
    if args.base and not re.fullmatch(r"[0-9a-f]{40}", args.base):
        parser.error("--base must be a full Git commit SHA")
    features = json.loads(MANIFEST.read_text(encoding="utf-8"))
    finish(check(features))
    if args.base:
        review_changes(features, args.base)
    print(f"Verified status, documentation and source references for {len(features)} features.")


if __name__ == "__main__":
    main()
