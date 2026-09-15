from __future__ import annotations

import hashlib
import ipaddress
import json
import re
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Literal
from urllib.parse import parse_qsl, urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class PublicModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


def public_url(value: str) -> str:
    p = urlsplit(value)
    host = (p.hostname or "").lower().rstrip(".")
    if p.scheme not in {"http", "https"} or not host or p.username or p.password:
        raise ValueError("An absolute, credential-free HTTP(S) URL is required")
    if p.port not in {None, 80, 443} or host in {"localhost", "metadata.google.internal"}:
        raise ValueError("Unsafe URL target")
    if ":" in host or "." not in host or host.endswith((".localhost", ".local", ".internal", ".example", ".test", ".invalid")):
        raise ValueError("Unsafe or illustrative URL target")
    if any(host == reserved or host.endswith("." + reserved) for reserved in ("example.com", "example.org", "example.net")):
        raise ValueError("Illustrative domains cannot support a public release")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        if not address.is_global:
            raise ValueError("Non-public IP target")
    if any(ord(c) < 32 for c in value) or "\\" in value:
        raise ValueError("Malformed URL")
    sensitive = {"token", "access_token", "api_key", "apikey", "password", "authorization", "signature", "x-amz-signature"}
    if any(key.casefold() in sensitive for key, _ in parse_qsl(p.query)):
        raise ValueError("Credential-bearing source URLs cannot be published")
    return value


class Source(PublicModel):
    name: str = Field(min_length=1)
    title: str = Field(min_length=1)
    author: str = ""
    published_date: date
    url: str

    _url = field_validator("url")(public_url)


class Evidence(PublicModel):
    source_url: str
    passage: str = Field(min_length=1)
    excerpt: str = ""
    excerpt_rights: str = ""
    _url = field_validator("source_url")(public_url)

    @model_validator(mode="after")
    def permitted_excerpt(self):
        if self.excerpt and not self.excerpt_rights.strip():
            raise ValueError("Republished excerpts need an explicit permission or licence record")
        return self


def copy_claims(unit) -> list[str]:
    """Every reader sentence, including headlines and interpretation, needs a mapping."""
    fields = [unit.headline, unit.summary, unit.perspective, unit.thesis,
              unit.analogy_weakness, unit.counterexample]
    if unit.type == "pattern":
        fields += [m.contribution for m in unit.members] + [m.limitation for m in unit.members]
    return [sentence.strip() for field in fields for sentence in re.split(r"(?<=[.!?])\s+", field.strip()) if sentence.strip()]


class Claim(PublicModel):
    text: str = Field(min_length=1)
    evidence: list[Evidence] = Field(min_length=1)
    currency_indexes: list[int] = Field(default_factory=list)


class Member(PublicModel):
    proposition: str = Field(min_length=1)
    countries: list[str] = Field(min_length=1)
    role: str
    contribution: str
    limitation: str
    follow_up_reason: str = ""


class CurrencyAnnotation(PublicModel):
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    local_name: str = Field(min_length=1)
    local_amount: Decimal = Field(gt=0)
    local_per_usd: Decimal = Field(gt=0)
    rate_date: date
    source_name: str = Field(min_length=1)
    source_url: str
    _url = field_validator("source_url")(public_url)

    @field_validator("currency")
    @classmethod
    def no_eur(cls, value: str) -> str:
        if value in {"USD", "EUR"}:
            raise ValueError("Use local currency plus USD; no EUR annotation")
        return value

    def usd_text(self) -> str:
        amount = self.local_amount / self.local_per_usd
        rounded = amount.quantize(Decimal(1).scaleb(amount.adjusted() - 1), rounding=ROUND_HALF_UP)
        if rounded >= 1_000_000_000:
            return f"US${rounded / 1_000_000_000:g} billion"
        if rounded >= 1_000_000:
            return f"US${rounded / 1_000_000:g} million"
        return f"US${rounded:,.0f}"


class Unit(PublicModel):
    type: Literal["dispatch", "pattern", "fine_print"]
    headline: str = Field(min_length=1)
    countries: list[str] = Field(min_length=1)
    topics: list[str] = Field(default_factory=list)
    thesis: str = ""
    summary: str = Field(min_length=1)
    perspective: str = ""
    analogy_weakness: str = ""
    counterexample: str = ""
    members: list[Member] = Field(min_length=1)
    claims: list[Claim] = Field(min_length=1)
    sources: list[Source] = Field(min_length=1)
    currencies: list[CurrencyAnnotation] = Field(default_factory=list)

    @model_validator(mode="after")
    def editorial_integrity(self):
        if self.type == "dispatch" and len(self.members) != 1:
            raise ValueError("A dispatch contains one proposition")
        if self.type == "pattern":
            if not 3 <= len(self.members) <= 5 or not all((self.thesis.strip(), self.analogy_weakness.strip(), self.counterexample.strip())):
                raise ValueError("An earned Pattern needs 3–5 cases, a thesis, weakness and counterexample")
            if any(not m.contribution.strip() or not m.limitation.strip() for m in self.members):
                raise ValueError("Every Pattern case needs a contribution and limitation")
        urls = {s.url for s in self.sources}
        if any(e.source_url not in urls for c in self.claims for e in c.evidence):
            raise ValueError("Claim evidence must refer to a listed source")
        for claim in self.claims:
            if any(index < 0 or index >= len(self.currencies) for index in claim.currency_indexes):
                raise ValueError("Claim refers to an unknown frozen currency record")
            expected = {index for index, currency in enumerate(self.currencies) if currency.usd_text() in claim.text}
            if expected - set(claim.currency_indexes):
                raise ValueError("Dollar equivalents must map to their frozen currency records")
        mapped = {c.text.strip() for c in self.claims}
        if any(sentence not in mapped for sentence in copy_claims(self)):
            raise ValueError("Every reader sentence and headline needs an exact claim-to-source mapping")
        return self


class CorrectionNotice(PublicModel):
    date: date
    description: str = Field(min_length=1)


class Release(PublicModel):
    schema_version: Literal[1] = 1
    edition_date: date
    issue_number: int = Field(ge=1)
    published_at: datetime
    revision_number: int = Field(ge=1)
    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    title: str = Field(min_length=1)
    opener: str = ""
    units: list[Unit] = Field(min_length=1)
    corrections: list[CorrectionNotice] = Field(default_factory=list)

    @property
    def slug(self) -> str:
        return f"{self.edition_date.isoformat()}-{self.issue_number}"

    @property
    def path(self) -> str:
        return f"/issues/{self.slug}/"

    @property
    def core_updates(self) -> int:
        return sum(len(u.members) for u in self.units if u.type != "fine_print")

    @property
    def estimated_minutes(self) -> float:
        copy = " ".join([self.title, self.opener] + [" ".join([u.headline, u.thesis, u.summary, u.perspective, u.analogy_weakness, u.counterexample]) for u in self.units])
        return round(len(re.findall(r"\b[\w’'-]+\b", copy)) / 150, 1)

    def calculated_hash(self) -> str:
        payload = self.model_dump(mode="json", exclude={"content_hash", "published_at", "revision_number", "corrections"})
        return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()

    @model_validator(mode="after")
    def release_integrity(self):
        if self.published_at.tzinfo is None:
            raise ValueError("Publication timestamp must include a timezone")
        if self.published_at.date() < self.edition_date:
            raise ValueError("Publication cannot precede the edition date")
        if self.core_updates < 5 or sum(u.type == "pattern" for u in self.units) > 1 or sum(u.type == "fine_print" for u in self.units) > 1:
            raise ValueError("An edition needs five core updates and at most one Pattern/Fine Print")
        propositions = [m.proposition.strip().casefold() for u in self.units for m in u.members]
        if len(propositions) != len(set(propositions)):
            raise ValueError("Duplicate proposition within the edition")
        copy = " ".join([self.title, self.opener] + [" ".join(copy_claims(u)) for u in self.units])
        if re.search(r"DEMO-|EDITOR MUST|Location pending|\bEUR\b|€|\bplaceholder\b", copy, re.I):
            raise ValueError("Unfinished, demo or EUR copy cannot be released")
        serialised = self.model_dump_json()
        if re.search(r"sk-[A-Za-z0-9_-]{20,}|gh[pousr]_[A-Za-z0-9]{20,}|BEGIN [A-Z ]*PRIVATE KEY", serialised):
            raise ValueError("Possible credential in release content")
        if any(c.rate_date > self.edition_date for u in self.units for c in u.currencies):
            raise ValueError("FX rate cannot postdate the edition")
        if self.calculated_hash() != self.content_hash:
            raise ValueError("Release content checksum does not match")
        return self
