# -*- test-case-name: twisted.python.test.test_dist -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Distutils convenience functionality.

Don't use this outside of Twisted.

Maintainer: Christopher Armstrong

@var _EXTRA_OPTIONS: These are the actual package names and versions that will
    be used by C{extras_require}.  This is not passed to setup directly so that
    combinations of the packages can be created without the need to copy
    package names multiple times.

@var _EXTRAS_REQUIRE: C{extras_require} is a dictionary of items that can be
    passed to setup.py to install optional dependencies.  For example, to
    install the optional dev dependencies one would type::

        pip install -e ".[dev]"

    This has been supported by setuptools since 0.5a4.

@var _PLATFORM_INDEPENDENT: A list of all optional cross-platform dependencies,
    as setuptools version specifiers, used to populate L{_EXTRAS_REQUIRE}.
"""

import os
import platform
import sys

from distutils.command import build_scripts, build_ext
from distutils.errors import CompileError
from setuptools import setup as _setup
from setuptools import Extension

from twisted import copyright
from twisted.python.compat import execfile, _PY3

STATIC_PACKAGE_METADATA = dict(
    name="Twisted",
    version=copyright.version,
    description="An asynchronous networking framework written in Python",
    author="Twisted Matrix Laboratories",
    author_email="twisted-python@twistedmatrix.com",
    maintainer="Glyph Lefkowitz",
    maintainer_email="glyph@twistedmatrix.com",
    url="http://twistedmatrix.com/",
    license="MIT",
    long_description="""\
An extensible framework for Python programming, with special focus
on event-based network programming and multiprotocol integration.
""",
    classifiers=[
        "Programming Language :: Python :: 2.7",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.3",
        "Programming Language :: Python :: 3.4",
        "Programming Language :: Python :: 3.5",
    ],
)


_dev = [
    'pyflakes >= 1.0.0',
    'twisted-dev-tools >= 0.0.2',
    'python-subunit',
    'sphinx >= 1.3.1',
]

if not _PY3:
    # These modules do not yet work on Python 3.
    _dev += [
        'twistedchecker >= 0.4.0',
        'pydoctor >= 16.2.0',
    ]

_EXTRA_OPTIONS = dict(
    dev=_dev,
    tls=['pyopenssl >= 16.0.0',
         'service_identity',
         'idna >= 0.6'],
    conch=['gmpy',
           'pyasn1',
           'cryptography >= 0.9.1',
           'appdirs >= 1.4.0',
           ],
    soap=['soappy'],
    serial=['pyserial'],
    osx=['pyobjc'],
    windows=['pypiwin32'],
    http2=['h2 >= 2.3.0, < 3.0',
           'priority >= 1.1.0, < 2.0'],
)

_PLATFORM_INDEPENDENT = (
    _EXTRA_OPTIONS['tls'] +
    _EXTRA_OPTIONS['conch'] +
    _EXTRA_OPTIONS['soap'] +
    _EXTRA_OPTIONS['serial'] +
    _EXTRA_OPTIONS['http2']
)

_EXTRAS_REQUIRE = {
    'dev': _EXTRA_OPTIONS['dev'],
    'tls': _EXTRA_OPTIONS['tls'],
    'conch': _EXTRA_OPTIONS['conch'],
    'soap': _EXTRA_OPTIONS['soap'],
    'serial': _EXTRA_OPTIONS['serial'],
    'http2': _EXTRA_OPTIONS['http2'],
    'all_non_platform': _PLATFORM_INDEPENDENT,
    'osx_platform': (
        _EXTRA_OPTIONS['osx'] + _PLATFORM_INDEPENDENT
    ),
    'windows_platform': (
        _EXTRA_OPTIONS['windows'] + _PLATFORM_INDEPENDENT
    ),
}


class ConditionalExtension(Extension):
    """
    An extension module that will only be compiled if certain conditions are
    met.

    @param condition: A callable of one argument which returns True or False to
        indicate whether the extension should be built. The argument is an
        instance of L{build_ext_twisted}, which has useful methods for checking
        things about the platform.
    """
    def __init__(self, *args, **kwargs):
        self.condition = kwargs.pop("condition", lambda builder: True)
        Extension.__init__(self, *args, **kwargs)



def setup(**kw):
    """
    An alternative to distutils' setup() which is specially designed
    for Twisted subprojects.

    @param conditionalExtensions: Extensions to optionally build.
    @type conditionalExtensions: C{list} of L{ConditionalExtension}
    """
    return _setup(**get_setup_args(**kw))


def get_setup_args(**kw):
    if 'cmdclass' not in kw:
        kw['cmdclass'] = {'build_scripts': build_scripts_twisted}

    if "conditionalExtensions" in kw:
        extensions = kw["conditionalExtensions"]
        del kw["conditionalExtensions"]

        if 'ext_modules' not in kw:
            # This is a workaround for distutils behavior; ext_modules isn't
            # actually used by our custom builder.  distutils deep-down checks
            # to see if there are any ext_modules defined before invoking
            # the build_ext command.  We need to trigger build_ext regardless
            # because it is the thing that does the conditional checks to see
            # if it should build any extensions.  The reason we have to delay
            # the conditional checks until then is that the compiler objects
            # are not yet set up when this code is executed.
            kw["ext_modules"] = extensions

        class my_build_ext(build_ext_twisted):
            conditionalExtensions = extensions
        kw.setdefault('cmdclass', {})['build_ext'] = my_build_ext
    return kw


def getVersion(base):
    """
    Extract the version number.

    @rtype: str
    @returns: The version number of the project, as a string like
    "2.0.0".
    """
    vfile = os.path.join(base, '_version.py')
    ns = {'__name__': 'Nothing to see here'}
    execfile(vfile, ns)
    return ns['version'].base()



def getExtensions():
    """
    Get the C extensions used for Twisted.
    """
    extensions = [
        ConditionalExtension(
            "twisted.test.raiser",
            ["twisted/test/raiser.c"],
            condition=lambda _: _isCPython
        ),
        ConditionalExtension(
            "twisted.internet.iocpreactor.iocpsupport",
            ["twisted/internet/iocpreactor/iocpsupport/iocpsupport.c",
             "twisted/internet/iocpreactor/iocpsupport/winsock_pointers.c"],
            libraries=["ws2_32"],
            condition=lambda _: _isCPython and sys.platform == "win32"
        ),
        ConditionalExtension(
            "twisted.python._sendmsg",
            sources=["twisted/python/_sendmsg.c"],
            condition=lambda _: not _PY3 and sys.platform != "win32"
        ),
        ConditionalExtension(
            "twisted.runner.portmap",
            ["twisted/runner/portmap.c"],
            condition=(
                lambda builder: not _PY3 and builder._check_header("rpc/rpc.h")
            )
        ),
    ]

    return extensions



def getConsoleScripts():
    """
    Returns a list of scripts for Twisted.
    """
    scripts = [
        "cftp = twisted.conch.scripts.cftp:run",
        "ckeygen = twisted.conch.scripts.ckeygen:run",
        "conch = twisted.conch.scripts.conch:run",
        "mailmail = twisted.mail.scripts.mailmail:run",
        "pyhtmlizer = twisted.scripts.htmlizer:run",
        "tkconch = twisted.conch.scripts.tkconch:run"
    ]
    portedToPython3Scripts = [
        "trial = twisted.scripts.trial:run",
        "twist = twisted.application.twist._twist:Twist.main",
        "twistd = twisted.scripts.twistd:run",
    ]
    if _PY3:
        return portedToPython3Scripts
    else:
        return scripts + portedToPython3Scripts


## Helpers and distutil tweaks

class build_scripts_twisted(build_scripts.build_scripts):
    """
    Renames scripts so they end with '.py' on Windows.
    """
    def run(self):
        build_scripts.build_scripts.run(self)
        if not os.name == "nt":
            return
        for f in os.listdir(self.build_dir):
            fpath = os.path.join(self.build_dir, f)
            if not fpath.endswith(".py"):
                pypath = fpath + ".py"
                if os.path.exists(pypath):
                    os.unlink(pypath)
                os.rename(fpath, pypath)



class build_ext_twisted(build_ext.build_ext):
    """
    Allow subclasses to easily detect and customize Extensions to
    build at install-time.
    """

    def prepare_extensions(self):
        """
        Prepare the C{self.extensions} attribute (used by
        L{build_ext.build_ext}) by checking which extensions in
        I{conditionalExtensions} should be built.  In addition, if we are
        building on NT, define the WIN32 macro to 1.
        """
        # always define WIN32 under Windows
        if os.name == 'nt':
            self.define_macros = [("WIN32", 1)]
        else:
            self.define_macros = []

        # On Solaris 10, we need to define the _XOPEN_SOURCE and
        # _XOPEN_SOURCE_EXTENDED macros to build in order to gain access to
        # the msg_control, msg_controllen, and msg_flags members in
        # sendmsg.c. (according to
        # http://stackoverflow.com/questions/1034587).  See the documentation
        # of X/Open CAE in the standards(5) man page of Solaris.
        if sys.platform.startswith('sunos'):
            self.define_macros.append(('_XOPEN_SOURCE', 1))
            self.define_macros.append(('_XOPEN_SOURCE_EXTENDED', 1))

        self.extensions = [
            x for x in self.conditionalExtensions if x.condition(self)
        ]

        for ext in self.extensions:
            ext.define_macros.extend(self.define_macros)


    def build_extensions(self):
        """
        Check to see which extension modules to build and then build them.
        """
        self.prepare_extensions()
        build_ext.build_ext.build_extensions(self)


    def _remove_conftest(self):
        for filename in ("conftest.c", "conftest.o", "conftest.obj"):
            try:
                os.unlink(filename)
            except EnvironmentError:
                pass


    def _compile_helper(self, content):
        conftest = open("conftest.c", "w")
        try:
            with conftest:
                conftest.write(content)

            try:
                self.compiler.compile(["conftest.c"], output_dir='')
            except CompileError:
                return False
            return True
        finally:
            self._remove_conftest()


    def _check_header(self, header_name):
        """
        Check if the given header can be included by trying to compile a file
        that contains only an #include line.
        """
        self.compiler.announce("checking for %s ..." % header_name, 0)
        return self._compile_helper("#include <%s>\n" % header_name)



def _checkCPython(sys=sys, platform=platform):
    """
    Checks if this implementation is CPython.

    This uses C{platform.python_implementation}.

    This takes C{sys} and C{platform} kwargs that by default use the real
    modules. You shouldn't care about these -- they are for testing purposes
    only.

    @return: C{False} if the implementation is definitely not CPython, C{True}
        otherwise.
    """
    return platform.python_implementation() == "CPython"


_isCPython = _checkCPython()
