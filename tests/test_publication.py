"""Isolated synthetic inputs for schema tests; never saved in releases/ or deployed."""
from datetime import date, datetime, timezone
from pathlib import Path
from decimal import Decimal
import json
import hashlib
import shutil

import pytest
from pydantic import ValidationError

from outside_headlines.build import build, load_releases
from outside_headlines.schema import CorrectionNotice, CurrencyAnnotation, Evidence, Release, Unit, public_url

ROOT = Path(__file__).resolve().parents[1]


def test_input(number=1, revision=1):
    units = []
    for i in range(5):
        url = "https://www.uspto.gov/trademarks/search"
        units.append(Unit.model_validate({"type": "dispatch", "headline": f"Schema test item {number}-{i}",
            "countries": ["United States"], "summary": "Synthetic test input, not an editorial release.",
            "members": [{"proposition": f"Test input {number}-{i}", "countries": ["United States"],
                         "role": "primary", "contribution": "", "limitation": ""}],
            "claims": [{"text": text, "evidence": [{"source_url": url, "passage": "Test locator"}]} for text in [f"Schema test item {number}-{i}", "Synthetic test input, not an editorial release."]],
            "sources": [{"name": "USPTO", "title": "Search", "published_date": "2026-09-14", "url": url}]}))
    value = Release.model_construct(schema_version=1, edition_date=date(2026, 9, 14), issue_number=number,
        published_at=datetime(2026, 9, 15, tzinfo=timezone.utc), revision_number=revision,
        content_hash="0" * 64, title="Synthetic schema test", opener="", units=units, corrections=[])
    value.content_hash = value.calculated_hash()
    return Release.model_validate(value.model_dump(mode="json"))

test_input.__test__ = False


def checkout(tmp_path):
    root = tmp_path / "checkout"
    root.mkdir()
    for folder in ["templates", "assets"]:
        shutil.copytree(ROOT / folder, root / folder)
    shutil.copy(ROOT / "site.json", root / "site.json")
    (root / "releases").mkdir()
    return root


def write(root, release):
    (root / "releases" / f"{release.slug}-r{release.revision_number}.json").write_text(release.model_dump_json())


@pytest.mark.parametrize("url", ["javascript:alert(1)", "http://127.0.0.1/", "http://169.254.169.254/", "https://localhost/", "https://secret@example.org/", "https://server.internal/", "https://host.test/", "https://example.org:9000/", "https://news.example.com/story", "https://www.uspto.gov/?access_token=private"])
def test_unsafe_links(url):
    with pytest.raises(ValueError):
        public_url(url)


def test_unknown_private_fields_and_checksum_fail():
    data = test_input().model_dump(mode="json")
    data["editor_minutes"] = 80
    with pytest.raises(ValidationError):
        Release.model_validate(data)
    del data["editor_minutes"]
    data["units"][0]["summary"] = "Changed after review."
    with pytest.raises(ValidationError):
        Release.model_validate(data)


def test_missing_provenance_duplicate_and_pattern_gates():
    data = test_input().model_dump(mode="json")
    data["units"][0]["claims"][0]["evidence"] = []
    with pytest.raises(ValidationError):
        Release.model_validate(data)
    data = test_input().model_dump(mode="json")
    data["units"][1]["members"] = data["units"][0]["members"]
    with pytest.raises(ValidationError, match="Duplicate"):
        Release.model_validate(data)
    data = test_input().units[0].model_dump(mode="json")
    data["type"] = "pattern"
    with pytest.raises(ValidationError, match="Pattern"):
        Unit.model_validate(data)


def test_currency_rounding_and_no_eur():
    data = {"currency": "NGN", "local_name": "naira", "local_amount": "18000000000",
            "local_per_usd": "1500", "rate_date": "2026-09-14", "source_name": "Central Bank of Nigeria",
            "source_url": "https://www.cbn.gov.ng/"}
    currency = CurrencyAnnotation.model_validate(data)
    assert currency.usd_text() == "US$12 million"
    assert currency.local_amount / currency.local_per_usd == Decimal("12000000")
    data["currency"] = "EUR"
    with pytest.raises(ValidationError):
        CurrencyAnnotation.model_validate(data)


def test_build_escapes_copy_and_collapses_evidence(tmp_path):
    root = checkout(tmp_path)
    release = test_input()
    release.units[0].summary = '<script>alert("unsafe")</script>'
    release.units[0].claims[1].text = release.units[0].summary
    release.content_hash = release.calculated_hash()
    write(root, release)
    build(root)
    text = (root / "dist" / release.path.lstrip("/") / "index.html").read_text()
    assert "<script>" not in text and "&lt;script&gt;" in text
    assert text.count('<details class="evidence">') == 5
    assert "<details open" not in text
    assert "Claim 1" not in text and "Quality gates" not in text
    assert "United States" in text and "Published" in text
    assert (root / "dist/feed.xml").read_text().count("<item>") == 1


def test_legacy_source_display_defaults_do_not_change_release_hash():
    data = test_input().model_dump(mode="json")
    for unit in data["units"]:
        for source in unit["sources"]:
            source.pop("display")
    payload = {k: v for k, v in data.items() if k not in {"content_hash", "published_at", "revision_number", "corrections"}}
    data["content_hash"] = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
    release = Release.model_validate(data)
    assert release.units[0].sources[0].display == "reporting"
    assert release.calculated_hash() == data["content_hash"]
    data["units"][0]["sources"][0]["display"] = "evidence_only"
    with pytest.raises(ValidationError, match="checksum"):
        Release.model_validate(data)


def test_supporting_sources_and_author_credits_are_inside_evidence(tmp_path):
    root = checkout(tmp_path)
    release = test_input()
    release.units[0].sources[0].display = "evidence_only"
    release.units[0].sources[0].author = "Test document credit"
    release.units[1].sources[0].author = "Test reporter credit"
    release.content_hash = release.calculated_hash()
    write(root, release)
    build(root)
    html = (root / "dist" / release.path.lstrip("/") / "index.html").read_text()
    import re
    visible = re.sub(r'<details class="evidence">.*?</details>', "", html, flags=re.S)
    assert "Test document credit" not in visible and "Test reporter credit" not in visible
    assert "Test document credit" in html and "Test reporter credit" in html
    assert html.count('<details class="evidence">') == 5
    assert "\u2014" not in html


def test_about_back_story_precedes_sources_and_preserves_requested_copy(tmp_path):
    root = checkout(tmp_path)
    build(root)
    html = (root / "dist/about/index.html").read_text()
    assert "For readers who follow the news and want to read outside the repeated and narrow confines of the headlines." in html
    assert "markets and ordinary life.</p>" in html
    assert "bored with its repeated choices" not in html
    assert "that deserve attention beyond" not in html
    assert "An unfamiliar location is not" not in html
    assert "Each edition is a finite collection" not in html
    assert "a Pattern brings them together" not in html
    assert "Humor is optional." not in html
    assert '<h2 id="back-story">Our back story</h2>' in html
    assert html.index("Our back story") < html.index("Sources and corrections")
    assert "places you'd never heard of, or dynamics that you hadn't considered" in html
    assert "you learned more than you would have learned from reading a hundred more headlines" in html
    assert "yesterday's headlines. I wanted to be able to recreate" in html
    assert "AI's ability to search the depths of the internet" in html
    assert "selection, presentation, and overall direction" in html
    assert "factual checking" not in html
    assert "have not yet been established through reader testing" not in html
    assert "This is an early publication experiment." in html
    assert "Private page preview" not in html and "Review and approve" not in html
    assert "\u2014" not in html


def test_empty_site_and_deterministic_reruns(tmp_path):
    root = checkout(tmp_path)
    build(root)
    first = {str(p.relative_to(root / "dist")): p.read_bytes() for p in (root / "dist").rglob("*") if p.is_file()}
    build(root)
    assert first == {str(p.relative_to(root / "dist")): p.read_bytes() for p in (root / "dist").rglob("*") if p.is_file()}
    assert "forthcoming" in (root / "dist/index.html").read_text()
    assert "isn’t here" in (root / "dist/404.html").read_text()
    assert (root / "dist/about/index.html").exists()
    assert (root / "dist/archive/index.html").exists()


def test_homepage_features_latest_and_two_previous_editions(tmp_path):
    root = checkout(tmp_path)
    for number in range(1, 5):
        write(root, test_input(number=number))
    build(root)
    html = (root / "dist/index.html").read_text()
    latest = "/issues/2026-09-14-4/"
    previous = ["/issues/2026-09-14-3/", "/issues/2026-09-14-2/"]
    oldest = "/issues/2026-09-14-1/"
    assert "The latest edition" in html and "Previous editions" in html
    assert all(path in html for path in [latest, *previous])
    assert oldest not in html
    assert html.index(latest) < html.index(previous[0]) < html.index(previous[1])
    assert 'href="/archive/"' in html


def test_preview_is_not_indexable(tmp_path):
    root = checkout(tmp_path)
    build(root, preview=True)
    assert 'name="robots" content="noindex,nofollow"' in (root / "dist/index.html").read_text()
    assert "Disallow: /" in (root / "dist/robots.txt").read_text()


def test_revision_sorting_corrections_and_navigation(tmp_path):
    root = checkout(tmp_path)
    first = test_input()
    write(root, first)
    replacement = test_input(revision=10)
    replacement.corrections = [CorrectionNotice(date=date(2026, 9, 15), description="A test correction.")]
    replacement = Release.model_validate(replacement.model_dump(mode="json"))
    write(root, replacement)
    second = test_input(number=2)
    write(root, second)
    editions = build(root)
    assert [r.issue_number for r in editions] == [2, 1]
    assert editions[1].revision_number == 10
    assert "A test correction" in (root / "dist" / first.path.lstrip("/") / "index.html").read_text()
    assert "Older: No. 1" in (root / "dist" / second.path.lstrip("/") / "index.html").read_text()


def test_public_tree_has_no_editorial_release_before_signoff():
    # A release is never required to build/deploy the empty shell.
    for path in (ROOT / "releases").glob("*.json"):
        Release.model_validate_json(path.read_text())
    for forbidden in ["back_pages.db", ".env", "src/back_pages", "data/source_registry.csv"]:
        assert not (ROOT / forbidden).exists()


def test_every_reader_sentence_and_excerpt_rights_required():
    data = test_input().units[0].model_dump(mode="json")
    data["perspective"] = "An unmapped assertion."
    with pytest.raises(ValidationError, match="exact claim"):
        Unit.model_validate(data)
    with pytest.raises(ValidationError, match="permission"):
        Evidence(source_url="https://www.uspto.gov/", passage="Test locator", excerpt="Unpermitted text")


def test_dollar_equivalent_requires_frozen_rate_mapping():
    data = test_input().units[0].model_dump(mode="json")
    data["summary"] = "The amount is about US$12 million."
    data["claims"][1]["text"] = data["summary"]
    data["currencies"] = [{"currency": "NGN", "local_name": "naira", "local_amount": "18000000000",
        "local_per_usd": "1500", "rate_date": "2026-09-14", "source_name": "CBN",
        "source_url": "https://www.cbn.gov.ng/"}]
    with pytest.raises(ValidationError, match="frozen currency"):
        Unit.model_validate(data)
    data["claims"][1]["currency_indexes"] = [0]
    Unit.model_validate(data)
