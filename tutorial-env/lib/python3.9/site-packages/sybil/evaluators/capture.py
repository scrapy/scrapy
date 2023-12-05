from sybil import Example


def evaluate_capture(example: Example) -> None:
    name, text = example.parsed
    example.namespace[name] = text
