
def start_python_console(namespace=None, noipython=False, banner=None):
    """Start Python console bound to the given namespace. If IPython or
    bpython are available, they will be started instead, unless `noipython`
    is True. If both IPython and bpython are available, IPython will be
    preferred. If neither is available, the built in console will be used,
    with tab completion enabled if on a system with readline.
    """
    if namespace is None:
        namespace = {}
    if banner is None:
        banner = ''

    try:
        try: # use IPython if available
            if noipython:
                raise ImportError()

            try:
                from IPython.terminal.embed import InteractiveShellEmbed
                from IPython.terminal.ipapp import load_default_config
            except ImportError:
                from IPython.frontend.terminal.embed import InteractiveShellEmbed
                from IPython.frontend.terminal.ipapp import load_default_config

        except ImportError:
            pass
        else:
            config = load_default_config()
            shell = InteractiveShellEmbed(
                banner1=banner, user_ns=namespace, config=config)
            shell()
            return

        try:
            import bpython
        except ImportError:
            pass
        else:
            # start bpython
            bpython.embed(locals_=namespace, banner=banner)
            return

        import code
        try: # readline module is only available on unix systems
            import readline
        except ImportError:
            pass
        else:
            import rlcompleter
            readline.parse_and_bind("tab:complete")
        code.interact(banner=banner, local=namespace)
    except SystemExit: # raised when using exit() in python code.interact
        pass
