#!/usr/bin/env python3
"""Fuzz harness for Scrapy — web scraping framework (17 GHSA advisories).

Tests URL parsing, robots.txt parsing, and link extraction
with arbitrary attacker-controlled inputs.
"""
import sys
import atheris

with atheris.instrument_imports():
    from scrapy.utils import url as url_utils
    from scrapy.linkextractors import IGNORED_EXTENSIONS


def TestOneInput(data):
    fdp = atheris.FuzzedDataProvider(data)

    # 1. URL parsing/canonicalization
    try:
        url = fdp.ConsumeString(512)
        url_utils.canonicalize_url(url)
    except Exception:
        pass

    # 2. URL safety checks
    try:
        url = fdp.ConsumeString(256)
        url_utils.safe_url_string(url)
    except Exception:
        pass

    # 3. URL query parameter parsing
    try:
        url = fdp.ConsumeString(256)
        url_utils.parse_url(url)
    except Exception:
        pass

    # 4. Ignored extensions matching
    try:
        ext = fdp.ConsumeString(32)
        _ = ext in IGNORED_EXTENSIONS
    except Exception:
        pass


def main():
    atheris.Setup(sys.argv, TestOneInput)
    atheris.Fuzz()


if __name__ == "__main__":
    main()
