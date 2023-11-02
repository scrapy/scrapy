from typing import Any, Callable, NoReturn


def obsolete_setter(setter: Callable, attrname: str) -> Callable[[Any, Any], NoReturn]:
    def newsetter(self: Any, value: Any) -> NoReturn:
        c = self.__class__.__name__
        msg = f"{c}.{attrname} is not modifiable, use {c}.replace() instead"
        raise AttributeError(msg)

    return newsetter
