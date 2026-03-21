def lprint_(obj, x, debug=False):
    buff = ''

    if obj is not None:
        if isinstance(obj, str):
            buff += f"[{obj}] "
        elif hasattr(obj, '__class__'):
            if hasattr(obj.__class__, '__name__'):
                buff += f"[{obj.__class__.__name__}] "

    if isinstance(x, str):
        buff += x
    else:
        buff += f"{str(x)} type={str(type(x))}"
    return buff

def lprint(obj, x, debug=False):
    buff = lprint_(obj, x, debug=debug)
    if buff is not None: print(buff)
