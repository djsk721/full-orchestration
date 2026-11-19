"""Check source navigation, local resources, and the built bilingual site."""

import argparse
import json
import re
from dataclasses import dataclass, field
from functools import lru_cache
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urljoin, urlsplit

import markdown
import yaml

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs"
LANGUAGES = ("ko", "en")
ROOT_PAIRS = {"README.md": "README.en.md", "CONTRIBUTING.md": "CONTRIBUTING.en.md"}
REQUIRED = (
    "index.md", "faq.md", "roadmap.md", "troubleshooting/index.md",
    "user-guide/getting-started.md", "user-guide/providers.md", "user-guide/mcp.md",
    "user-guide/orchestration.md", "user-guide/managed-harness.md", "user-guide/background.md",
    "admin-guide/operations.md", "admin-guide/configuration.md", "developer-guide/architecture.md",
    "developer-guide/testing.md", "developer-guide/documentation.md",
)


def pages(locale):
    directory = DOCS / locale
    return {path.relative_to(directory).as_posix() for path in directory.rglob("*.md")}


def github_slug(title, separator):
    value = re.sub(r"[^\w\- ]", "", title.lower())
    return value.replace(" ", separator)


@dataclass
class Reference:
    tag: str
    url: str
    attrs: dict


@dataclass
class Parsed(HTMLParser):
    ids: set = field(default_factory=set)
    links: list = field(default_factory=list)
    headings: list = field(default_factory=list)
    language: str = ""

    def __post_init__(self):
        super().__init__()
        self.heading = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if identifier := attrs.get("id") or (attrs.get("name") if tag == "a" else None):
            self.ids.add(identifier)
        for attribute in ("href", "src"):
            if value := attrs.get(attribute):
                self.links.append(Reference(tag, value, attrs))
        if re.fullmatch("h[1-6]", tag):
            self.heading = (int(tag[1]), [])
        if tag == "html":
            self.language = attrs.get("lang", "")

    def handle_endtag(self, tag):
        if self.heading and tag == f"h{self.heading[0]}":
            level, words = self.heading
            self.headings.append((level, "".join(words).strip()))
            self.heading = None

    def handle_data(self, data):
        if self.heading:
            self.heading[1].append(data)


@lru_cache
def parse(path):
    content = path.read_text(encoding="utf-8")
    if path.suffix == ".md":
        content = markdown.markdown(
            content, extensions=["fenced_code", "tables", "toc", "attr_list"],
            extension_configs={"toc": {"slugify": github_slug}},
        )
    parsed = Parsed()
    parsed.feed(content)
    return parsed


def nav_entries(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for child in value:
            yield from nav_entries(child)
    elif isinstance(value, dict):
        for child in value.values():
            yield from nav_entries(child)


def source_checks():
    errors = []
    needed = {ROOT / name for name in [*ROOT_PAIRS, *ROOT_PAIRS.values(), "LICENSE", "CHANGELOG.md"]}
    needed |= {DOCS / lang / path for lang in LANGUAGES for path in REQUIRED}
    needed |= {DOCS / "assets" / path for path in ("images/mark.svg", "screenshots/dashboard.png")}
    needed |= {DOCS / "internal" / path for path in (
        "documentation-inventory.md", "documentation-implementation-report.md", "legacy-readme.md",
    )}
    for path in sorted(needed):
        if not path.is_file():
            errors.append(f"{path.relative_to(ROOT)}: required file missing")
    # Read navigation as data without interpreting the Python-specific extension configuration.
    config = yaml.compose((ROOT / "mkdocs.yml").read_text(encoding="utf-8"))
    nav_node = next((v for k, v in config.value if k.value == "nav"), None)
    if nav_node is None:
        errors.append("mkdocs.yml: no navigation defined")
    else:
        navigation = yaml.safe_load(yaml.serialize(nav_node))
        entries = list(nav_entries(navigation))
        if len(set(entries)) != len(entries):
            errors.append("mkdocs.yml: duplicate navigation page")
        for lang in LANGUAGES:
            for path in sorted(pages(lang) - set(entries)):
                errors.append(f"docs/{lang}/{path}: missing navigation entry")
            for path in sorted(set(entries) - pages(lang)):
                errors.append(f"mkdocs.yml: missing navigation target docs/{lang}/{path}")

    markdown_files = set(ROOT.glob("*.md")) | set(DOCS.rglob("*.md")) | set((ROOT / ".github").glob("*.md"))
    remote_links = set()
    for path in sorted(markdown_files):
        for ref in parse(path).links:
            parts = urlsplit(ref.url)
            if parts.scheme or parts.netloc:
                if parts.scheme in ("http", "https"):
                    remote_links.add(ref.url)
                continue
            location = unquote(parts.path)
            target = (path.parent / location).resolve() if location else path
            label = f"{path.relative_to(ROOT)}: {ref.url}"
            if not target.is_relative_to(ROOT) or not target.exists():
                errors.append(f"{label}: missing local {ref.tag} target")
            elif ref.tag == "img" and not target.is_file():
                errors.append(f"{label}: image must be a file")
            elif parts.fragment and target.suffix == ".md" and unquote(parts.fragment) not in parse(target).ids:
                errors.append(f"{label}: unknown heading or anchor")
    for left, right in ROOT_PAIRS.items():
        for source, target in ((left, right), (right, left)):
            path = ROOT / source
            if path.is_file() and not any(ref.url == target for ref in parse(path).links):
                errors.append(f"{source}: language link to {target} missing")
    print(f"Checked {len(markdown_files)} Markdown files. {len(remote_links)} external URLs left to network review.")
    return errors


def output_route(relative, locale):
    directory = "" if locale == "ko" else "en/"
    if relative == "index.md":
        return directory
    return directory + relative.removesuffix(".md").removesuffix("/index") + "/"


def site_checks(site, base):
    errors = []
    prefix = "/" + base.strip("/") + "/" if base.strip("/") else "/"
    origin = "https://docs.invalid"
    html_files = set(site.rglob("*.html"))
    routes = {
        prefix + output_route(path, lang): lang for lang in LANGUAGES for path in pages(lang)
    }
    expected = {site / route.removeprefix(prefix) / "index.html" for route in routes}
    expected.add(site / "404.html")
    for missing in sorted(expected - html_files):
        errors.append(f"{missing.relative_to(site)}: expected HTML missing")
    for extra in sorted(html_files - expected):
        errors.append(f"{extra.relative_to(site)}: unexpected published HTML")
    for file in sorted(html_files):
        name = file.relative_to(site).as_posix()
        path = prefix + (name if file.name != "index.html" else name.removesuffix("index.html"))
        document = parse(file)
        language = routes.get(path)
        if language and (document.language != language or not document.headings or document.headings[0][0] != 1):
            errors.append(f"{name}: expected a {language} page with a level-one title")
        switches = {}
        for ref in document.links:
            url = urlsplit(urljoin(origin + path, ref.url))
            if url.netloc != "docs.invalid" or url.scheme != "https":
                continue
            dest = unquote(url.path)
            if not dest.startswith(prefix):
                errors.append(f"{name}: {ref.url} escapes the site base {prefix}")
                continue
            route = dest.removeprefix(prefix)
            if "md-select__link" in ref.attrs.get("class", ""):
                switches[ref.attrs.get("hreflang")] = dest if dest.endswith("/") else dest + "/"
            target = site / route
            if target.is_dir():
                target /= "index.html"
            if not target.is_file():
                errors.append(f"{name}: broken generated link or asset {ref.url}")
            elif url.fragment and target.suffix == ".html" and unquote(url.fragment) not in parse(target).ids:
                errors.append(f"{name}: broken generated anchor {ref.url}")
        if language:
            relative = path.removeprefix(prefix + ("en/" if language == "en" else ""))
            expected_switches = {"ko": prefix + relative, "en": prefix + "en/" + relative}
            if switches != expected_switches:
                errors.append(f"{name}: unmatched language switch targets {switches}")
    index = site / "search/search_index.json"
    if not index.is_file():
        errors.append("search/search_index.json: search index missing")
    else:
        records = json.loads(index.read_text(encoding="utf-8"))["docs"]
        indexed = {prefix + item["location"] for item in records if "#" not in item["location"]}
        for route in sorted(routes.keys() - indexed):
            errors.append(f"search/search_index.json: {route} not indexed")
        if not any(re.search("[가-힣]", row["title"]) for row in records):
            errors.append("search/search_index.json: no Korean titles indexed")
    print(f"Checked {len(html_files)} rendered HTML files under {prefix}.")
    return errors


def finish(errors):
    if errors:
        for error in errors:
            print(error)
        raise SystemExit(1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site", type=Path, help="verify a previously built site")
    parser.add_argument("--base", default="/", help="URL path prefix used to build the supplied site")
    args = parser.parse_args()
    finish(site_checks(args.site.resolve(), args.base) if args.site else source_checks())


if __name__ == "__main__":
    main()
