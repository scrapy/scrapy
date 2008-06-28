import simplejson

def test_listrecursion():
    x = []
    x.append(x)
    try:
        simplejson.dumps(x)
    except ValueError:
        pass
    else:
        assert False, "didn't raise ValueError on list recursion"
    x = []
    y = [x]
    x.append(y)
    try:
        simplejson.dumps(x)
    except ValueError:
        pass
    else:
        assert False, "didn't raise ValueError on alternating list recursion"
    y = []
    x = [y, y]
    # ensure that the marker is cleared
    simplejson.dumps(x)

def test_dictrecursion():
    x = {}
    x["test"] = x
    try:
        simplejson.dumps(x)
    except ValueError:
        pass
    else:
        assert False, "didn't raise ValueError on dict recursion"
    x = {}
    y = {"a": x, "b": x}
    # ensure that the marker is cleared
    simplejson.dumps(x)

class TestObject:
    pass

class RecursiveJSONEncoder(simplejson.JSONEncoder):
    recurse = False
    def default(self, o):
        if o is TestObject:
            if self.recurse:
                return [TestObject]
            else:
                return 'TestObject'
        simplejson.JSONEncoder.default(o)

def test_defaultrecursion():
    enc = RecursiveJSONEncoder()
    assert enc.encode(TestObject) == '"TestObject"'
    enc.recurse = True
    try:
        enc.encode(TestObject)
    except ValueError:
        pass
    else:
        assert False, "didn't raise ValueError on default recursion"
