#!/usr/bin/env python3
"""Normalize public company URLs into conservative domain identities."""

from __future__ import annotations

import argparse
import ipaddress
from urllib.parse import urlparse

from common import ValidationError

COMMON_SERVICE_SUBDOMAINS = {"www", "shop", "store", "m", "mobile", "app", "en", "us"}
COMMON_MULTIPART_SUFFIXES = {
    "co.uk", "org.uk", "com.au", "net.au", "co.nz", "co.jp", "co.kr",
    "com.br", "com.mx", "co.in", "com.sg", "com.hk", "co.za", "com.tr",
}
SHARED_HOSTING_DOMAINS = {"blogspot.com", "github.io", "myshopify.com", "netlify.app", "pages.dev", "vercel.app", "wordpress.com"}


def normalize_domain(value: str) -> str:
    raw = str(value or "").strip().lower()
    if not raw:
        raise ValidationError("Domain or URL is required.")
    parsed = urlparse(raw if "://" in raw else f"//{raw}", scheme="https")
    host = (parsed.hostname or "").rstrip(".")
    if not host or " " in host or "." not in host:
        raise ValidationError(f"Cannot normalize domain from {value!r}.")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise ValidationError("IP addresses are not accepted as company identities.")
    try:
        host = host.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise ValidationError("Domain contains invalid international characters.") from exc
    labels = [part for part in host.split(".") if part]
    while len(labels) > 2 and labels[0] in COMMON_SERVICE_SUBDOMAINS:
        labels.pop(0)
    suffix = ".".join(labels[-2:])
    if suffix in SHARED_HOSTING_DOMAINS and len(labels) >= 3:
        return ".".join(labels)
    if suffix in COMMON_MULTIPART_SUFFIXES and len(labels) >= 3:
        return ".".join(labels[-3:])
    return ".".join(labels[-2:])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("value")
    args = parser.parse_args()
    try:
        print(normalize_domain(args.value))
    except ValidationError as exc:
        raise SystemExit(f"Validation error: {exc}") from exc


if __name__ == "__main__":
    main()
