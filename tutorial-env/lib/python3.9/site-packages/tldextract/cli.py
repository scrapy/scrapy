"""tldextract CLI."""

import argparse
import dataclasses
import json
import logging
import os.path
import pathlib
import sys

from ._version import version as __version__
from .tldextract import TLDExtract


def main() -> None:
    """Tldextract CLI main command."""
    logging.basicConfig()

    parser = argparse.ArgumentParser(
        prog="tldextract", description="Parse hostname from a url or fqdn"
    )

    parser.add_argument(
        "--version", action="version", version="%(prog)s " + __version__
    )
    parser.add_argument(
        "-j",
        "--json",
        default=False,
        action="store_true",
        help="output in json format",
    )
    parser.add_argument(
        "input", metavar="fqdn|url", type=str, nargs="*", help="fqdn or url"
    )

    parser.add_argument(
        "-u",
        "--update",
        default=False,
        action="store_true",
        help="force fetch the latest TLD definitions",
    )
    parser.add_argument(
        "--suffix_list_url",
        action="append",
        required=False,
        help="use an alternate URL or local file for TLD definitions",
    )
    parser.add_argument(
        "-c", "--cache_dir", help="use an alternate TLD definition caching folder"
    )
    parser.add_argument(
        "-p",
        "--include_psl_private_domains",
        "--private_domains",
        default=False,
        action="store_true",
        help="Include private domains",
    )
    parser.add_argument(
        "--no_fallback_to_snapshot",
        default=True,
        action="store_false",
        dest="fallback_to_snapshot",
        help="Don't fall back to the package's snapshot of the suffix list",
    )

    args = parser.parse_args()

    obj_kwargs = {
        "include_psl_private_domains": args.include_psl_private_domains,
        "fallback_to_snapshot": args.fallback_to_snapshot,
    }

    if args.cache_dir:
        obj_kwargs["cache_dir"] = args.cache_dir

    if args.suffix_list_url is not None:
        suffix_list_urls = []
        for source in args.suffix_list_url:
            if os.path.isfile(source):
                as_path_uri = pathlib.Path(os.path.abspath(source)).as_uri()
                suffix_list_urls.append(as_path_uri)
            else:
                suffix_list_urls.append(source)

        obj_kwargs["suffix_list_urls"] = suffix_list_urls

    tld_extract = TLDExtract(**obj_kwargs)

    if args.update:
        tld_extract.update(True)
    elif not args.input:
        parser.print_usage()
        sys.exit(1)

    for i in args.input:
        ext = tld_extract(i)
        if args.json:
            properties = ("fqdn", "ipv4", "ipv6", "registered_domain")
            print(
                json.dumps(
                    {
                        **dataclasses.asdict(ext),
                        **{prop: getattr(ext, prop) for prop in properties},
                    }
                )
            )
        else:
            print(f"{ext.subdomain} {ext.domain} {ext.suffix}")
