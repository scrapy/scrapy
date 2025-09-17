from __future__ import annotations

import code
from collections.abc import Callable
from functools import wraps
from typing import TYPE_CHECKING, Any

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.theme import Theme

if TYPE_CHECKING:
    from collections.abc import Iterable

EmbedFuncT = Callable[..., None]
KnownShellsT = dict[str, Callable[..., EmbedFuncT]]

# Scrapy-specific color theme
SCRAPY_THEME = Theme({
    "success": "bold green",
    "error": "bold red",
    "warning": "bold yellow",
    "info": "cyan",
    "spider": "magenta",
    "url": "blue underline",
    "filename": "green",
    "number": "bright_blue",
    "scrapy": "bold green",
})

# Shared console instances
console = Console(theme=SCRAPY_THEME, stderr=True)
stdout_console = Console(theme=SCRAPY_THEME, stderr=False)

def get_console(use_stderr: bool = True) -> Console:
    """Get a themed console instance.

    Args:
        use_stderr: If True, output to stderr (default). If False, output to stdout.

    Returns:
        Console instance with Scrapy theme.
    """
    return console if use_stderr else stdout_console


def get_progress() -> Progress:
    """Get a progress instance for long-running operations.

    Returns:
        Progress instance with spinner and progress bar.
    """
    return Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    )


def _embed_ipython_shell(
    namespace: dict[str, Any] = {}, banner: str = ""
) -> EmbedFuncT:
    """Start an IPython Shell"""
    try:
        from IPython.terminal.embed import InteractiveShellEmbed  # noqa: T100,PLC0415
        from IPython.terminal.ipapp import load_default_config  # noqa: PLC0415
    except ImportError:
        from IPython.frontend.terminal.embed import (  # type: ignore[no-redef]  # noqa: T100,PLC0415
            InteractiveShellEmbed,
        )
        from IPython.frontend.terminal.ipapp import (  # type: ignore[no-redef]  # noqa: PLC0415
            load_default_config,
        )

    @wraps(_embed_ipython_shell)
    def wrapper(namespace: dict[str, Any] = namespace, banner: str = "") -> None:
        config = load_default_config()
        # Always use .instance() to ensure _instance propagation to all parents
        # this is needed for <TAB> completion works well for new imports
        # and clear the instance to always have the fresh env
        # on repeated breaks like with inspect_response()
        InteractiveShellEmbed.clear_instance()
        shell = InteractiveShellEmbed.instance(
            banner1=banner, user_ns=namespace, config=config
        )
        shell()

    return wrapper


def _embed_bpython_shell(
    namespace: dict[str, Any] = {}, banner: str = ""
) -> EmbedFuncT:
    """Start a bpython shell"""
    import bpython  # noqa: PLC0415

    @wraps(_embed_bpython_shell)
    def wrapper(namespace: dict[str, Any] = namespace, banner: str = "") -> None:
        bpython.embed(locals_=namespace, banner=banner)

    return wrapper


def _embed_ptpython_shell(
    namespace: dict[str, Any] = {}, banner: str = ""
) -> EmbedFuncT:
    """Start a ptpython shell"""
    import ptpython.repl  # noqa: PLC0415  # pylint: disable=import-error

    @wraps(_embed_ptpython_shell)
    def wrapper(namespace: dict[str, Any] = namespace, banner: str = "") -> None:
        print(banner)
        ptpython.repl.embed(locals=namespace)

    return wrapper


def _embed_standard_shell(
    namespace: dict[str, Any] = {}, banner: str = ""
) -> EmbedFuncT:
    """Start a standard python shell"""
    try:  # readline module is only available on unix systems
        import readline  # noqa: PLC0415
    except ImportError:
        pass
    else:
        import rlcompleter  # noqa: F401,PLC0415

        readline.parse_and_bind("tab:complete")  # type: ignore[attr-defined]

    @wraps(_embed_standard_shell)
    def wrapper(namespace: dict[str, Any] = namespace, banner: str = "") -> None:
        code.interact(banner=banner, local=namespace)

    return wrapper


DEFAULT_PYTHON_SHELLS: KnownShellsT = {
    "ptpython": _embed_ptpython_shell,
    "ipython": _embed_ipython_shell,
    "bpython": _embed_bpython_shell,
    "python": _embed_standard_shell,
}


def get_shell_embed_func(
    shells: Iterable[str] | None = None, known_shells: KnownShellsT | None = None
) -> EmbedFuncT | None:
    """Return the first acceptable shell-embed function
    from a given list of shell names.
    """
    if shells is None:  # list, preference order of shells
        shells = DEFAULT_PYTHON_SHELLS.keys()
    if known_shells is None:  # available embeddable shells
        known_shells = DEFAULT_PYTHON_SHELLS.copy()
    for shell in shells:
        if shell in known_shells:
            try:
                # function test: run all setup code (imports),
                # but dont fall into the shell
                return known_shells[shell]()
            except ImportError:
                continue
    return None


def start_python_console(
    namespace: dict[str, Any] | None = None,
    banner: str = "",
    shells: Iterable[str] | None = None,
) -> None:
    """Start Python console bound to the given namespace.
    Readline support and tab completion will be used on Unix, if available.
    """
    if namespace is None:
        namespace = {}

    try:
        shell = get_shell_embed_func(shells)
        if shell is not None:
            shell(namespace=namespace, banner=banner)
    except SystemExit:  # raised when using exit() in python code.interact
        pass
