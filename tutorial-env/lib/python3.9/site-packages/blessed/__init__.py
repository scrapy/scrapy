"""
A thin, practical wrapper around terminal capabilities in Python.

http://pypi.python.org/pypi/blessed
"""
# std imports
import sys as _sys
import platform as _platform

# isort: off
if _platform.system() == 'Windows':
    from blessed.win_terminal import Terminal
else:
    from blessed.terminal import Terminal  # type: ignore

if (3, 0, 0) <= _sys.version_info[:3] < (3, 2, 3):
    # Good till 3.2.10
    # Python 3.x < 3.2.3 has a bug in which tparm() erroneously takes a string.
    raise ImportError('Blessed needs Python 3.2.3 or greater for Python 3 '
                      'support due to http://bugs.python.org/issue10570.')

__all__ = ('Terminal',)
__version__ = "1.20.0"
