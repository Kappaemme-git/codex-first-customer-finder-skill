#!/usr/bin/env python3
"""Normalize company names and public social handles for comparison."""

from __future__ import annotations

import argparse
import re
import unicodedata
from urllib.parse import urlparse

from common import ValidationError

LEGAL_SUFFIXES = {
    "inc", "incorporated", "llc", "ltd", "limited", "corp", "corporation",
    "company", "co", "plc", "gmbh", "ag", "sa", "sarl", "lp", "llp", "holdings",
}


def normalize_company_name(value: str) -> str:
    raw = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode("ascii").lower()
    words = re.findall(r"[a-z0-9]+", raw.replace("&", " and "))
    while words and words[-1] in LEGAL_SUFFIXES:
        words.pop()
    if not words:
        raise ValidationError("Company name has no comparable characters.")
    return " ".join(words)


def normalize_social_handle(value: str) -> str:
    raw = str(value or "").strip().lower()
    if "://" in raw:
        parsed = urlparse(raw)
        raw = parsed.path
    handle = raw.strip("/@ ").split("/")[0]
    handle = re.sub(r"[^a-z0-9._-]", "", handle)
    if not handle:
        raise ValidationError("Social handle is empty or invalid.")
    return handle


def aliases_match(left: str, right: str) -> bool:
    return normalize_company_name(left) == normalize_company_name(right)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("value")
    parser.add_argument("--social", action="store_true")
    args = parser.parse_args()
    try:
        print(normalize_social_handle(args.value) if args.social else normalize_company_name(args.value))
    except ValidationError as exc:
        raise SystemExit(f"Validation error: {exc}") from exc


if __name__ == "__main__":
    main()
