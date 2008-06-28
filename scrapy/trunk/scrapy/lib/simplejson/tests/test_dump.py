from cStringIO import StringIO
import simplejson as S

def test_dump():
    sio = StringIO()
    S.dump({}, sio)
    assert sio.getvalue() == '{}'
    
def test_dumps():
    assert S.dumps({}) == '{}'
