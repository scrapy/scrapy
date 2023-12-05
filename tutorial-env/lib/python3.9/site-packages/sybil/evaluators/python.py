from typing import Sequence
import __future__

from sybil import Example


def pad(source: str, line: int) -> str:
    """
    Pad the supplied source such that line numbers will be based on the one provided
    when the source is evaluated.
    """
    # There must be a nicer way to get line numbers to be correct...
    return line  * '\n' + source


class PythonEvaluator:

    def __init__(self, future_imports: Sequence[str] = ()) -> None:
        self.flags = 0
        for future_import in future_imports:
            self.flags |= getattr(__future__, future_import).compiler_flag

    def __call__(self, example: Example) -> None:
        # There must be a nicer way to get line numbers to be correct...
        source = pad(example.parsed, example.line + example.parsed.line_offset)
        code = compile(source, example.path, 'exec', flags=self.flags, dont_inherit=True)
        exec(code, example.namespace)
        # exec adds __builtins__, we don't want it:
        del example.namespace['__builtins__']
