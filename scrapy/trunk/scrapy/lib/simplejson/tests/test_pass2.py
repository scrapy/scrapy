# from http://json.org/JSON_checker/test/pass2.json
JSON = r'''
[[[[[[[[[[[[[[[[[[["Not too deep"]]]]]]]]]]]]]]]]]]]
'''

def test_parse():
    # test in/out equivalence and parsing
    import simplejson
    res = simplejson.loads(JSON)
    out = simplejson.dumps(res)
    assert res == simplejson.loads(out)
