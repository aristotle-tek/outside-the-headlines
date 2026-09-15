from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from email.utils import format_datetime
from xml.etree import ElementTree as ET

from jinja2 import Environment, FileSystemLoader, select_autoescape

from .schema import Release, public_url

NAME = "Outside the Headlines"
TAGLINE = "Insights from the long tail."


def load_releases(root: Path) -> list[Release]:
    latest: dict[str, Release] = {}
    records = []
    for path in sorted((root / "releases").glob("*.json")):
        release = Release.model_validate_json(path.read_text())
        if path.name != f"{release.slug}-r{release.revision_number}.json":
            raise ValueError(f"Release filename does not match its identity: {path.name}")
        records.append(release)
    for release in sorted(records, key=lambda r: (r.slug, r.revision_number)):
        previous = latest.get(release.slug)
        if previous:
            if release.published_at != previous.published_at:
                raise ValueError("A correction must retain the initial publication timestamp")
            if not release.corrections:
                raise ValueError("Replacement revisions need a public correction notice")
            if release.corrections[:-1] != previous.corrections:
                raise ValueError("Correction history must be retained")
        if not previous or release.revision_number > previous.revision_number:
            latest[release.slug] = release
    editions = sorted(latest.values(), key=lambda r: (r.edition_date, r.issue_number), reverse=True)
    used: set[str] = set()
    for edition in reversed(editions):
        for unit in edition.units:
            for member in unit.members:
                key = member.proposition.strip().casefold()
                if key in used and not member.follow_up_reason.strip():
                    raise ValueError("A repeated proposition needs a follow-up reason")
                used.add(key)
    if len({r.issue_number for r in editions}) != len(editions):
        raise ValueError("Issue numbers must be unique")
    return editions


def build(root: Path, output: Path | None = None, *, base_url: str | None = None, preview: bool = False) -> list[Release]:
    config = json.loads((root / "site.json").read_text())
    base = public_url(base_url or config["base_url"]).rstrip("/")
    output = output or root / "dist"
    if output.resolve() == root.resolve() or root.resolve() not in output.resolve().parents:
        raise ValueError("Build output must be a subdirectory of this repository")
    releases = load_releases(root)
    env = Environment(loader=FileSystemLoader(root / "templates"), autoescape=select_autoescape(["html", "xml"]))
    env.globals.update(name=NAME, tagline=TAGLINE, base_url=base, preview=preview)
    output.mkdir(parents=True, exist_ok=True)
    # Remove only stale generated HTML/XML files; never wipe the checkout.
    for path in output.rglob("*"):
        if path.is_file() and path.suffix in {".html", ".xml"}:
            path.unlink()
    shutil.copytree(root / "assets", output / "assets", dirs_exist_ok=True)

    def page(path, template, **values):
        target = output / path.lstrip("/")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(env.get_template(template).render(**values), encoding="utf-8")

    page("index.html", "home.html", releases=releases, canonical="/", title=NAME)
    page("archive/index.html", "archive.html", releases=releases, canonical="/archive/", title="Archive")
    page("about/index.html", "about.html", canonical="/about/", title="About")
    page("404.html", "404.html", canonical=None, title="Page not found")
    for index, release in enumerate(releases):
        page(release.path + "index.html", "issue.html", issue=release, canonical=release.path, title=release.title,
             newer=releases[index - 1] if index else None,
             older=releases[index + 1] if index + 1 < len(releases) else None)
    rss = ET.Element("rss", version="2.0")
    channel = ET.SubElement(rss, "channel")
    for tag, value in (("title", NAME), ("link", base + "/"), ("description", TAGLINE), ("language", "en")):
        ET.SubElement(channel, tag).text = value
    for release in releases:
        item = ET.SubElement(channel, "item")
        for tag, value in (("title", release.title), ("link", base + release.path), ("description", release.opener), ("pubDate", format_datetime(release.published_at))):
            ET.SubElement(item, tag).text = value
        ET.SubElement(item, "guid", isPermaLink="true").text = base + release.path
    ET.ElementTree(rss).write(output / "feed.xml", encoding="utf-8", xml_declaration=True)
    sitemap = ET.Element("urlset", xmlns="http://www.sitemaps.org/schemas/sitemap/0.9")
    for path in ["/", "/archive/", "/about/"] + [r.path for r in releases]:
        node = ET.SubElement(sitemap, "url")
        ET.SubElement(node, "loc").text = base + path
    ET.ElementTree(sitemap).write(output / "sitemap.xml", encoding="utf-8", xml_declaration=True)
    (output / "robots.txt").write_text("User-agent: *\nDisallow: /\n" if preview else f"User-agent: *\nAllow: /\nSitemap: {base}/sitemap.xml\n")
    return releases


def main():
    root = Path(__file__).resolve().parents[1]
    preview = os.environ.get("VERCEL_ENV") == "preview"
    build(root, preview=preview)
