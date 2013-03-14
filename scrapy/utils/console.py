
def start_python_console(namespace=None, noipython=False):
    """Start Python console binded to the given namespace. If bpython is
    available, a bpython console will be started instead, with an IPython
    console as a fallback unless `noipython` is True. Also, tab completion
    will be used on Unix systems.
    """
    if namespace is None:
        namespace = {}
    try:
        try:
            if noipython:
                raise ImportError
            try: # use bpython if available
                import bpython
                bpython.embed(locals_=namespace)
            except ImportError: # use IPython if available
                import IPython
                try:
                    IPython.embed(user_ns=namespace)
                except AttributeError:
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
