class A:
    def a(self):
        return "a"


class B(A):
    def b(self):
        return "b"


class Inherit(A):
    def a(self):
        return "c"
