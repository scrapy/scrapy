"""
(c) 2008-2013, holger krekel
"""


class XSpec:
    """Execution Specification: key1=value1//key2=value2 ...
    * keys need to be unique within the specification scope
    * neither key nor value are allowed to contain "//"
    * keys are not allowed to contain "="
    * keys are not allowed to start with underscore
    * if no "=value" is given, assume a boolean True value
    """

    # XXX allow customization, for only allow specific key names
    popen = (
        ssh
    ) = socket = python = chdir = nice = dont_write_bytecode = execmodel = None

    def __init__(self, string):
        self._spec = string
        self.env = {}
        for keyvalue in string.split("//"):
            i = keyvalue.find("=")
            if i == -1:
                key, value = keyvalue, True
            else:
                key, value = keyvalue[:i], keyvalue[i + 1 :]
            if key[0] == "_":
                raise AttributeError("%r not a valid XSpec key" % key)
            if key in self.__dict__:
                raise ValueError(f"duplicate key: {key!r} in {string!r}")
            if key.startswith("env:"):
                self.env[key[4:]] = value
            else:
                setattr(self, key, value)

    def __getattr__(self, name):
        if name[0] == "_":
            raise AttributeError(name)
        return None

    def __repr__(self):
        return f"<XSpec {self._spec!r}>"

    def __str__(self):
        return self._spec

    def __hash__(self):
        return hash(self._spec)

    def __eq__(self, other):
        return self._spec == getattr(other, "_spec", None)

    def __ne__(self, other):
        return self._spec != getattr(other, "_spec", None)

    def _samefilesystem(self):
        return self.popen is not None and self.chdir is None
