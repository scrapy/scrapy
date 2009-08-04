"""Some common reducers"""

def take_first(values):
    for value in values:
        if value:
            return value

def identity(values):
    return values

def join_strings(values):
    return u' '.join(values)
