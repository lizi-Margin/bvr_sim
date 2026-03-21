from typing import Union, List, Tuple

def iterable_eq(a,b):
    if len(a) != len(b):
        return False
    for i in range(len(a)):
        if a[i] != b[i]:
            return False
    return True

def iterable_prod(xs):
    out = 1
    for x in xs: out *= x
    return out

def to_int(obj: Union[List, Tuple]):
    if isinstance(obj, tuple):
        obj = list(obj)
        for i in range(len(obj)):
            obj[i] = int(obj[i])
        return tuple(obj)
    elif isinstance(obj, list):
        for i in range(len(obj)):
            obj[i] = int(obj[i])
        return obj
    else:
        assert False