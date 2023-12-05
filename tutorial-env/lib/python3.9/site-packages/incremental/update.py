# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

from __future__ import absolute_import, division, print_function

import click
import os
import datetime
from typing import TYPE_CHECKING, Dict, Optional, Callable, Iterable

from incremental import Version

if TYPE_CHECKING:
    from typing_extensions import Protocol

    class _ReadableWritable(Protocol):
        def read(self):  # type: () -> bytes
            pass

        def write(self, v):  # type: (bytes) -> object
            pass

        def __enter__(self):  # type: () -> _ReadableWritable
            pass

        def __exit__(self, *args, **kwargs):  # type: (object, object) -> Optional[bool]
            pass

    # FilePath is missing type annotations
    # https://twistedmatrix.com/trac/ticket/10148
    class FilePath(object):
        def __init__(self, path):  # type: (str) -> None
            self.path = path

        def child(self, v):  # type: (str) -> FilePath
            pass

        def isdir(self):  # type: () -> bool
            pass

        def isfile(self):  # type: () -> bool
            pass

        def getContent(self):  # type: () -> bytes
            pass

        def open(self, mode):  # type: (str) -> _ReadableWritable
            pass

        def walk(self):  # type: () -> Iterable[FilePath]
            pass


else:
    from twisted.python.filepath import FilePath

_VERSIONPY_TEMPLATE = '''"""
Provides {package} version information.
"""

# This file is auto-generated! Do not edit!
# Use `python -m incremental.update {package}` to change this file.

from incremental import Version

__version__ = {version_repr}
__all__ = ["__version__"]
'''

_YEAR_START = 2000


def _findPath(path, package):  # type: (str, str) -> FilePath

    cwd = FilePath(path)

    src_dir = cwd.child("src").child(package.lower())
    current_dir = cwd.child(package.lower())

    if src_dir.isdir():
        return src_dir
    elif current_dir.isdir():
        return current_dir
    else:
        raise ValueError(
            "Can't find under `./src` or `./`. Check the "
            "package name is right (note that we expect your "
            "package name to be lower cased), or pass it using "
            "'--path'."
        )


def _existing_version(path):  # type: (FilePath) -> Version
    version_info = {}  # type: Dict[str, Version]

    with path.child("_version.py").open("r") as f:
        exec(f.read(), version_info)

    return version_info["__version__"]


def _run(
    package,  # type: str
    path,  # type: Optional[str]
    newversion,  # type: Optional[str]
    patch,  # type: bool
    rc,  # type: bool
    post,  # type: bool
    dev,  # type: bool
    create,  # type: bool
    _date=None,  # type: Optional[datetime.date]
    _getcwd=None,  # type: Optional[Callable[[], str]]
    _print=print,  # type: Callable[[object], object]
):  # type: (...) -> None

    if not _getcwd:
        _getcwd = os.getcwd

    if not _date:
        _date = datetime.date.today()

    if type(package) != str:
        package = package.encode("utf8")  # type: ignore[assignment]

    _path = FilePath(path) if path else _findPath(_getcwd(), package)

    if (
        newversion
        and patch
        or newversion
        and dev
        or newversion
        and rc
        or newversion
        and post
    ):
        raise ValueError("Only give --newversion")

    if dev and patch or dev and rc or dev and post:
        raise ValueError("Only give --dev")

    if (
        create
        and dev
        or create
        and patch
        or create
        and rc
        or create
        and post
        or create
        and newversion
    ):
        raise ValueError("Only give --create")

    if newversion:
        from pkg_resources import parse_version

        existing = _existing_version(_path)
        st_version = parse_version(newversion)._version  # type: ignore[attr-defined]

        release = list(st_version.release)

        minor = 0
        micro = 0
        if len(release) == 1:
            (major,) = release
        elif len(release) == 2:
            major, minor = release
        else:
            major, minor, micro = release

        v = Version(
            package,
            major,
            minor,
            micro,
            release_candidate=st_version.pre[1] if st_version.pre else None,
            post=st_version.post[1] if st_version.post else None,
            dev=st_version.dev[1] if st_version.dev else None,
        )

    elif create:
        v = Version(package, _date.year - _YEAR_START, _date.month, 0)
        existing = v

    elif rc and not patch:
        existing = _existing_version(_path)

        if existing.release_candidate:
            v = Version(
                package,
                existing.major,
                existing.minor,
                existing.micro,
                existing.release_candidate + 1,
            )
        else:
            v = Version(package, _date.year - _YEAR_START, _date.month, 0, 1)

    elif patch:
        existing = _existing_version(_path)
        v = Version(
            package,
            existing.major,
            existing.minor,
            existing.micro + 1,
            1 if rc else None,
        )

    elif post:
        existing = _existing_version(_path)

        if existing.post is None:
            _post = 0
        else:
            _post = existing.post + 1

        v = Version(package, existing.major, existing.minor, existing.micro, post=_post)

    elif dev:
        existing = _existing_version(_path)

        if existing.dev is None:
            _dev = 0
        else:
            _dev = existing.dev + 1

        v = Version(
            package,
            existing.major,
            existing.minor,
            existing.micro,
            existing.release_candidate,
            dev=_dev,
        )

    else:
        existing = _existing_version(_path)

        if existing.release_candidate:
            v = Version(package, existing.major, existing.minor, existing.micro)
        else:
            raise ValueError("You need to issue a rc before updating the major/minor")

    NEXT_repr = repr(Version(package, "NEXT", 0, 0)).split("#")[0].replace("'", '"')
    NEXT_repr_bytes = NEXT_repr.encode("utf8")

    version_repr = repr(v).split("#")[0].replace("'", '"')
    version_repr_bytes = version_repr.encode("utf8")

    existing_version_repr = repr(existing).split("#")[0].replace("'", '"')
    existing_version_repr_bytes = existing_version_repr.encode("utf8")

    _print("Updating codebase to %s" % (v.public()))

    for x in _path.walk():

        if not x.isfile():
            continue

        original_content = x.getContent()
        content = original_content

        # Replace previous release_candidate calls to the new one
        if existing.release_candidate:
            content = content.replace(existing_version_repr_bytes, version_repr_bytes)
            content = content.replace(
                (package.encode("utf8") + b" " + existing.public().encode("utf8")),
                (package.encode("utf8") + b" " + v.public().encode("utf8")),
            )

        # Replace NEXT Version calls with the new one
        content = content.replace(NEXT_repr_bytes, version_repr_bytes)
        content = content.replace(
            NEXT_repr_bytes.replace(b"'", b'"'), version_repr_bytes
        )

        # Replace <package> NEXT with <package> <public>
        content = content.replace(
            package.encode("utf8") + b" NEXT",
            (package.encode("utf8") + b" " + v.public().encode("utf8")),
        )

        if content != original_content:
            _print("Updating %s" % (x.path,))
            with x.open("w") as f:
                f.write(content)

    _print("Updating %s/_version.py" % (_path.path))
    with _path.child("_version.py").open("w") as f:
        f.write(
            (
                _VERSIONPY_TEMPLATE.format(package=package, version_repr=version_repr)
            ).encode("utf8")
        )


@click.command()
@click.argument("package")
@click.option("--path", default=None)
@click.option("--newversion", default=None)
@click.option("--patch", is_flag=True)
@click.option("--rc", is_flag=True)
@click.option("--post", is_flag=True)
@click.option("--dev", is_flag=True)
@click.option("--create", is_flag=True)
def run(
    package,  # type: str
    path,  # type: Optional[str]
    newversion,  # type: Optional[str]
    patch,  # type: bool
    rc,  # type: bool
    post,  # type: bool
    dev,  # type: bool
    create,  # type: bool
):  # type: (...) -> None
    return _run(
        package=package,
        path=path,
        newversion=newversion,
        patch=patch,
        rc=rc,
        post=post,
        dev=dev,
        create=create,
    )


if __name__ == "__main__":  # pragma: no cover
    run()
