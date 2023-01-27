"""Helper functions for working with templates"""

from os import PathLike
import re
import string
from pathlib import Path
from urllib.parse import urlparse
from typing import Union


def render_templatefile(path: Union[str, PathLike], url=None, **kwargs):
    path_obj = Path(path)
    raw = path_obj.read_text("utf8")

    if url is not None:
        if urlparse(url).scheme in ["https", "http"]:
            # make template match the correct url
            raw = re.sub(r"start_urls = \[.*?\]", "start_urls = ['$url']", raw)
            kwargs["url"] = url

    content = string.Template(raw).substitute(**kwargs)

    render_path = path_obj.with_suffix("") if path_obj.suffix == ".tmpl" else path_obj

    if path_obj.suffix == ".tmpl":
        path_obj.rename(render_path)

    render_path.write_text(content, "utf8")


CAMELCASE_INVALID_CHARS = re.compile(r"[^a-zA-Z\d]")


def string_camelcase(string):
    """Convert a word  to its CamelCase version and remove invalid chars

    >>> string_camelcase('lost-pound')
    'LostPound'

    >>> string_camelcase('missing_images')
    'MissingImages'

    """
    return CAMELCASE_INVALID_CHARS.sub("", string.title())
