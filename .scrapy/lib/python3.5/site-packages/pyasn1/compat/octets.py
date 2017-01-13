from sys import version_info

if version_info[0] <= 2:
    int2oct = chr
    ints2octs = lambda s: ''.join([ int2oct(x) for x in s ])
    null = ''
    oct2int = ord
    octs2ints = lambda s: [ oct2int(x) for x in s ]
    str2octs = lambda x: x
    octs2str = lambda x: x
    isOctetsType = lambda s: isinstance(s, str)
    isStringType = lambda s: isinstance(s, (str, unicode))
else:
    ints2octs = bytes
    int2oct = lambda x: ints2octs((x,))
    null = ints2octs()
    oct2int = lambda x: x
    octs2ints = lambda s: [ x for x in s ]
    str2octs = lambda x: x.encode()
    octs2str = lambda x: x.decode()
    isOctetsType = lambda s: isinstance(s, bytes)
    isStringType = lambda s: isinstance(s, str)
