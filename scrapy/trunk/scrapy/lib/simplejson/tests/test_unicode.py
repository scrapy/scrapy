import simplejson as S

def test_encoding1():
    encoder = S.JSONEncoder(encoding='utf-8')
    u = u'\N{GREEK SMALL LETTER ALPHA}\N{GREEK CAPITAL LETTER OMEGA}'
    s = u.encode('utf-8')
    ju = encoder.encode(u)
    js = encoder.encode(s)
    assert ju == js
    
def test_encoding2():
    u = u'\N{GREEK SMALL LETTER ALPHA}\N{GREEK CAPITAL LETTER OMEGA}'
    s = u.encode('utf-8')
    ju = S.dumps(u, encoding='utf-8')
    js = S.dumps(s, encoding='utf-8')
    assert ju == js
