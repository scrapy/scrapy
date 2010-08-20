
def start_python_console(namespace=None, noipython=False):
    """Start Python console binded to the given namespace. If IPython is
    available, an IPython console will be started instead, unless `noipython`
    is True. Also, tab completion will be used on Unix systems.
    """
    if namespace is None:
        namespace = {}
    try:
        try: # use IPython if available
            if noipython:
                raise ImportError
            import IPython
            shell = IPython.Shell.IPShellEmbed(argv=[], user_ns=namespace)
            shell()
        except ImportError:
            import code
            try: # readline module is only available on unix systems
                import readline
            except ImportError:
                pass
            else:
                import rlcompleter
                readline.parse_and_bind("tab:complete")
            code.interact(banner='', local=namespace)
    except SystemExit: # raised when using exit() in python code.interact
        pass
