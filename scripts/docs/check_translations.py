"""Validate bilingual pairs and record explicitly reviewed translations."""

import argparse
import hashlib
import json
import re

from check_doc_structure import DOCS, LANGUAGES, ROOT, ROOT_PAIRS, finish, pages, parse

MANIFEST = DOCS / "internal/translations.json"


def snapshot(path):
    # Normalize checkout line endings so Windows and Linux compare identically.
    normalized = path.read_text(encoding="utf-8")
    return {
        "sha256": hashlib.sha256(normalized.encode()).hexdigest(),
        "headings": [title for _, title in parse(path).headings],
    }


def inspect_pair(ko, en):
    left, right = parse(ko).headings, parse(en).headings
    errors = []
    levels = [level for level, _ in left]
    if not levels or levels[0] != 1 or levels.count(1) != 1 or levels != [level for level, _ in right]:
        errors.append("expected one corresponding title and matching heading levels and section order")
    if ko.read_text(encoding="utf-8") == en.read_text(encoding="utf-8"):
        errors.append("files have identical content")
    if not re.search("[가-힣]", ko.read_text(encoding="utf-8")):
        errors.append("Korean source contains no Hangul")
    if not re.search(r"[A-Za-z]", "".join(title for _, title in right)):
        errors.append("English page contains no English headings")
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ack", nargs="+", metavar="PAIR", help="record hashes and headings of reviewed pairs")
    args = parser.parse_args()
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8")) if MANIFEST.exists() else {}
    ko_pages, en_pages = (pages(lang) for lang in LANGUAGES)
    errors = [f"docs/en/{path}: missing English translation" for path in sorted(ko_pages - en_pages)]
    errors += [f"docs/ko/{path}: missing Korean source" for path in sorted(en_pages - ko_pages)]
    pairs = {path: (DOCS / "ko" / path, DOCS / "en" / path) for path in ko_pages & en_pages}
    pairs.update({ko: (ROOT / ko, ROOT / en) for ko, en in ROOT_PAIRS.items()})

    for key in sorted(pairs):
        ko, en = pairs[key]
        missing = [path.relative_to(ROOT) for path in (ko, en) if not path.is_file()]
        if missing:
            errors.extend(f"{path}: translation pair file missing" for path in missing)
            continue
        errors.extend(f"{key}: {error}" for error in inspect_pair(ko, en))
        current = {"ko": snapshot(ko), "en": snapshot(en)}
        if args.ack and key in args.ack:
            manifest[key] = current
        elif not args.ack and manifest.get(key) != current:
            changed = [lang for lang in LANGUAGES if manifest.get(key, {}).get(lang) != current[lang]]
            errors.append(f"{key}: translation review missing or stale ({', '.join(changed)}). Review both files, then use --ack {key}.")
    if args.ack:
        errors.extend(f"{key}: unknown translation pair" for key in sorted(set(args.ack) - pairs.keys()))
    errors.extend(f"{key}: obsolete translation review entry" for key in sorted(manifest.keys() - pairs.keys()))
    finish(errors)
    if args.ack:
        MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        print(f"Recorded review for {len(set(args.ack))} bilingual pairs.")
    else:
        print(f"Verified {len(pairs)} bilingual pairs against the review manifest.")


if __name__ == "__main__":
    main()
