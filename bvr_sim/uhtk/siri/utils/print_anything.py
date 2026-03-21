import pprint
import inspect
import numpy as np
from types import FunctionType, MethodType
from .is_basic_type import is_basic_type

def simple_print_obj(obj):
    for attr in dir(obj):
        if not attr.startswith('__'):
            value = getattr(obj, attr)
            print(f"{attr}: {value}")
            # print(f"{attr}")

def print_obj(obj, indent=0, deep=False, _recursive=True):
    prefix = " " * indent
    # obj_id = id(obj)

    if isinstance(obj, (int, float, bool, str, type(None))):
        print(f"{prefix}{repr(obj)}" )
        return

    if isinstance(obj, np.ndarray):
        print(f"{prefix}ndarray(shape={obj.shape}, dtype={obj.dtype})" )
        return

    if isinstance(obj, dict):
        print(f"{prefix}dict(len={len(obj)})" )
        return

    # list / tuple / set
    if isinstance(obj, (list, tuple, set)):
        typename = type(obj).__name__
        print(f"{prefix}{typename}(len={len(obj)})" )
        return

    if isinstance(obj, (FunctionType, MethodType)):
        sig = None
        try:
            sig = str(inspect.signature(obj))
        except Exception:
            sig = "()"
        print(f"{prefix}<function {obj.__name__}{sig}>" )
        return

    if inspect.isclass(obj):
        print(f"{prefix}<class {obj.__name__}>" )
        return

    if hasattr(obj, "__dict__") or hasattr(obj, "__slots__"):
        typename = type(obj).__name__
        print(f"{prefix}{typename} instance")
        if _recursive:
            for attr in dir(obj):
                if not attr.startswith('__'):
                    value = getattr(obj, attr)
                    print(f"{prefix}{attr}->")
                    print_obj(value, indent=indent+1, _recursive=deep)
                    # print(f"{attr}")
        return

    print(f"{prefix}{repr(obj)}" )


def print_dict(data ):
    summary = {
        key: f" {type(value)}, shape={value.shape}, dtype={value.dtype}" if isinstance(value, np.ndarray) 
                                                                         else type(value) 
                                                                         for key, value in data.items()
    }
    # try:
    pprint.pprint(summary, indent=1)
    # except:  ## if python < 3.10
    #     print(summary)


def print_list(data):
    assert isinstance(data, (list, np.ndarray))
    print("list len: ", len(data))
    # item_len = []
    # for item in data: item_len.append(len(item))
    # print(item_len)
    print("[", end="\n")
    for index, item in enumerate(data): 
        if hasattr(index, "__dict__") or hasattr(index, "__slots__"):
            print(f" {index}: instance type={type(data)}", end="\n")
        else:
            print_obj(item, indent=1, deep=False)
        # print(f" {index}: ", end="")
        # print_dict(vars(item))
        # print_obj(item, indent=1, deep=False)
    print("]")