import sys
import re
import functools
import distutils.core
import distutils.errors
import distutils.extension

from .dist import _get_unpatched
from . import msvc9_support

_Extension = _get_unpatched(distutils.core.Extension)

msvc9_support.patch_for_specialized_compiler()

def _have_cython():
    """
    Return True if Cython can be imported.
    """
    cython_impl = 'Cython.Distutils.build_ext',
    try:
        # from (cython_impl) import build_ext
        __import__(cython_impl, fromlist=['build_ext']).build_ext
        return True
    except Exception:
        pass
    return False

# for compatibility
have_pyrex = _have_cython


class Extension(_Extension):
    """Extension that uses '.c' files in place of '.pyx' files"""

    def _convert_pyx_sources_to_lang(self):
        """
        Replace sources with .pyx extensions to sources with the target
        language extension. This mechanism allows language authors to supply
        pre-converted sources but to prefer the .pyx sources.
        """
        if _have_cython():
            # the build has Cython, so allow it to compile the .pyx files
            return
        lang = self.language or ''
        target_ext = '.cpp' if lang.lower() == 'c++' else '.c'
        sub = functools.partial(re.sub, '.pyx$', target_ext)
        self.sources = list(map(sub, self.sources))

class Library(Extension):
    """Just like a regular Extension, but built as a library instead"""

distutils.core.Extension = Extension
distutils.extension.Extension = Extension
if 'distutils.command.build_ext' in sys.modules:
    sys.modules['distutils.command.build_ext'].Extension = Extension
