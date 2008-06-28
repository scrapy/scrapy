def test_script_close_attack():
    import simplejson
    res = simplejson.dumps('</script>')
    assert '</script>' not in res
    res = simplejson.dumps(simplejson.loads('"</script>"'))
    assert '</script>' not in res
