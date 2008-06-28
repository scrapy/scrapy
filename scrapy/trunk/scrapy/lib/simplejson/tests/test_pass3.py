# from http://json.org/JSON_checker/test/pass3.json
JSON = r'''
{
    "JSON Test Pattern pass3": {
        "The outermost value": "must be an object or array.",
        "In this test": "It is an object."
    }
}
'''

def test_parse():
    # test in/out equivalence and parsing
    import simplejson
    res = simplejson.loads(JSON)
    out = simplejson.dumps(res)
    assert res == simplejson.loads(out)
