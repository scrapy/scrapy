


def test_separators():
    import simplejson
    import textwrap
    
    h = [['blorpie'], ['whoops'], [], 'd-shtaeou', 'd-nthiouh', 'i-vhbjkhnth',
         {'nifty': 87}, {'field': 'yes', 'morefield': False} ]

    expect = textwrap.dedent("""\
    [
      [
        "blorpie"
      ] ,
      [
        "whoops"
      ] ,
      [] ,
      "d-shtaeou" ,
      "d-nthiouh" ,
      "i-vhbjkhnth" ,
      {
        "nifty" : 87
      } ,
      {
        "field" : "yes" ,
        "morefield" : false
      }
    ]""")


    d1 = simplejson.dumps(h)
    d2 = simplejson.dumps(h, indent=2, sort_keys=True, separators=(' ,', ' : '))

    h1 = simplejson.loads(d1)
    h2 = simplejson.loads(d2)

    assert h1 == h
    assert h2 == h
    assert d2 == expect
