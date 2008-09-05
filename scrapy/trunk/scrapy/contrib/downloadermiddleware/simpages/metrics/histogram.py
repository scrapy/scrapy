import math

def plot(data):
    """
    data is a dict of tuples of the form: {key: quantity, ...}.
    Make the histogram of the data dict.
    """
    maxv = max(data.values())
    minv = min(data.values())
    step = (maxv - minv) * 0.1 if (maxv - minv) != 0 else 1
    s = []
    for key, q in data.items():
        s1 = "%s%s: " % (key, blanks(6 - len(str(key))))
        for i in xrange(1, int(math.ceil(q/step)+1)):
            s1+= "="
        if s1[len(s1)-1] == '=':
            s1+= " " 
        s1 += str(q)
        s.append(s1)
    maxl = len(max(s, key=lambda x:len(x)))
    s2 = ''
    for i in xrange(1,maxl+1):
        s2 += '-'

    r = "\tgroup | quantities\n"
    r += "\t%s" % s2
    for x in s:
        r += "\n\t%s" % x
    return r

def blanks(n):
    return ''.join([' ' for x in range(1,n+1)])

def print_plot(data):
    print plot(data)




