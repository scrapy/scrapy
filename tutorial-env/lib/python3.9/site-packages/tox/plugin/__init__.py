"""
tox uses `pluggy <https://pluggy.readthedocs.io/en/stable/>`_ to customize the default behaviour. It provides an
extension mechanism for plugin management an calling hooks.

Pluggy discovers a plugin by looking up for entry-points named ``tox``, for example in a pyproject.toml:

.. code-block:: toml

    [project.entry-points.tox]
    your_plugin = "your_plugin.hooks"

Therefore, to start using a plugin, you solely need to install it in the same environment tox is running in and it will
be discovered via the defined entry-point (in the example above, tox will load ``your_plugin.hooks``).

A plugin is created by implementing extension points in the form of hooks. For example the following code snippet would
define a new ``--magic`` command line interface flag the user can specify:

.. code-block:: python

    from tox.config.cli.parser import ToxParser
    from tox.plugin import impl


    @impl
    def tox_add_option(parser: ToxParser) -> None:
        parser.add_argument("--magic", action="store_true", help="magical flag")

You can define such hooks either in a package installed alongside tox or within a ``toxfile.py`` found alongside your
tox configuration file (root of your project).
"""
from __future__ import annotations

from typing import Any, Callable, TypeVar

import pluggy

NAME = "tox"  #: the name of the tox hook

_F = TypeVar("_F", bound=Callable[..., Any])
impl: Callable[[_F], _F] = pluggy.HookimplMarker(NAME)  #: decorator to mark tox plugin hooks


__all__ = (
    "NAME",
    "impl",
)
