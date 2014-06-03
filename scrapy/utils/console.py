
def start_python_console(namespace=None, noipython=False, banner=''):
    """Start Python console binded to the given namespace. If IPython is
    available, an IPython console will be started instead, unless `noipython`
    is True. Also, tab completion will be used on Unix systems.
    """
    if namespace is None:
        namespace = {}

    try:
        try: # use IPython if available
            if noipython:
                raise ImportError()

            try:
                try:
                    from IPython.terminal import embed
                except ImportError:
                    from IPython.frontend.terminal import embed
                sh = embed.InteractiveShellEmbed(banner1=banner)
            except ImportError:
                from IPython.Shell import IPShellEmbed
                sh = IPShellEmbed(banner=banner)

            sh(global_ns={}, local_ns=namespace)
        except ImportError:
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
