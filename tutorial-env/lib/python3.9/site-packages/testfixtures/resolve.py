from operator import setitem
from typing import Any, Callable, Optional

from testfixtures import not_there


# Should be Literal[setattr, getattr] but Python 3.8 only.
Setter = Callable[[Any, str, Any], None]


class Resolved:

    def __init__(self, container: Any, setter: Setter, name: str, found: Any):
        self.container: Any = container
        self.setter: Setter = setter
        self.name: str = name
        self.found: Any = found

    def __repr__(self):
        return f'<Resolved: {self.found}>'


def resolve(dotted_name: str, container: Optional[Any] = None) -> Resolved:
    names = dotted_name.split('.')
    used = names.pop(0)
    if container is None:
        found = __import__(used)
        container = found
    else:
        assert not used, 'Absolute traversal not allowed when container supplied'
        used = ''
        found = container
    setter = None
    name = None
    for name in names:
        container = found
        used += '.' + name
        try:
            found = getattr(found, name)
            setter = setattr
        except AttributeError:
            try:
                __import__(used)
            except ImportError:
                setter = setitem
                try:
                    found = found[name]  # pragma: no branch
                except KeyError:
                    found = not_there  # pragma: no branch
                except TypeError:
                    try:
                        name = int(name)
                    except ValueError:
                        setter = setattr
                        found = not_there
                    else:
                        found = found[name]  # pragma: no branch
            else:
                found = getattr(found, name)
                setter = getattr
    return Resolved(container, setter, name, found)


class _Reference:

    @classmethod
    def classmethod(cls):  # pragma: no cover
        pass

    @staticmethod
    def staticmethod(cls):  # pragma: no cover
        pass


class_type = type(_Reference)
classmethod_type = type(_Reference.classmethod)
