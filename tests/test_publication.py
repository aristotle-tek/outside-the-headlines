"""Isolated synthetic inputs for schema tests; never saved in releases/ or deployed."""
from datetime import date, datetime, timezone
from pathlib import Path
from decimal import Decimal
import json
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


@pytest.mark.parametrize("url", ["javascript:alert(1)", "http://127.0.0.1/", "http://169.254.169.254/", "https://localhost/", "https://secret@example.org/", "https://server.internal/", "https://host.test/", "https://example.org:9000/", "https://news.example.com/story"])
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
