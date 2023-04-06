"""Helper functions for working with templates"""

import re
import string
from os import PathLike
from pathlib import Path
from typing import Union


def render_templatefile(path: Union[str, PathLike], **kwargs):
    path_obj = Path(path)
    raw = path_obj.read_text("utf8")

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
