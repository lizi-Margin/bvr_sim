def is_basic_type(obj):
    if (
        isinstance(obj, int) or isinstance(obj, bool) or isinstance(obj, str) 
        or isinstance(obj, list) or isinstance(obj, tuple) or isinstance(obj, dict)
        or (obj is None)
    ):
        return True
    else:
        return False