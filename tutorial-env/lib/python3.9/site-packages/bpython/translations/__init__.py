import gettext
import locale
import os.path
import sys
from typing import Optional, cast, List

from .. import package_dir

translator: gettext.NullTranslations = cast(gettext.NullTranslations, None)


def _(message) -> str:
    return translator.gettext(message)


def ngettext(singular, plural, n):
    return translator.ngettext(singular, plural, n)


def init(
    locale_dir: Optional[str] = None, languages: Optional[List[str]] = None
) -> None:
    try:
        locale.setlocale(locale.LC_ALL, "")
    except locale.Error:
        # This means that the user's environment is broken. Let's just continue
        # with the default C locale.
        sys.stderr.write(
            "Error: Your locale settings are not supported by "
            "the system. Using the fallback 'C' locale instead. "
            "Please fix your locale settings.\n"
        )

    global translator
    if locale_dir is None:
        locale_dir = os.path.join(package_dir, "translations")

    translator = gettext.translation(
        "bpython", locale_dir, languages, fallback=True
    )
