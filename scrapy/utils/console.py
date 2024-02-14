from functools import wraps


def _embed_ipython_shell(namespace={}, banner=""):
    """Start an IPython Shell"""
    try:
        from IPython.terminal.embed import InteractiveShellEmbed
        from IPython.terminal.ipapp import load_default_config
    except ImportError:
        from IPython.frontend.terminal.embed import InteractiveShellEmbed
        from IPython.frontend.terminal.ipapp import load_default_config

    @wraps(_embed_ipython_shell)
    def wrapper(namespace=namespace, banner=""):
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


def _embed_bpython_shell(namespace={}, banner=""):
    """Start a bpython shell"""
    import bpython

    @wraps(_embed_bpython_shell)
    def wrapper(namespace=namespace, banner=""):
        bpython.embed(locals_=namespace, banner=banner)

    return wrapper


def _embed_ptpython_shell(namespace={}, banner=""):
    """Start a ptpython shell"""
    import ptpython.repl

    @wraps(_embed_ptpython_shell)
    def wrapper(namespace=namespace, banner=""):
        print(banner)
        ptpython.repl.embed(locals=namespace)

    return wrapper


def _embed_standard_shell(namespace={}, banner=""):
    """Start a standard python shell"""
    import code

    try:  # readline module is only available on unix systems
        import readline
    except ImportError:
        pass
    else:
        import rlcompleter  # noqa: F401

        readline.parse_and_bind("tab:complete")

    @wraps(_embed_standard_shell)
    def wrapper(namespace=namespace, banner=""):
        code.interact(banner=banner, local=namespace)

    return wrapper


DEFAULT_PYTHON_SHELLS = {
    "ptpython": _embed_ptpython_shell,
    "ipython": _embed_ipython_shell,
    "bpython": _embed_bpython_shell,
    "python": _embed_standard_shell,
}


def get_shell_embed_func(shells=None, known_shells=None):
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


def start_python_console(namespace=None, banner="", shells=None):
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
