# machine info
import json
import uuid
import os
import time
import platform
import socket
import psutil

def get_mx_info():
    info = {
        'ExpUUID': uuid.uuid1().hex,
        'RunPath': os.getcwd(),
        'StartDateTime': time.strftime("%Y-%m-%d %H-%M-%S", time.localtime())
    }
    
    system_info = {
        'Platform': platform.platform(),
        'System': platform.system(),
        'NodeName': platform.node(),
        'Release': platform.release(),
        'Version': platform.version(),
        'Machine': platform.machine(),
        'Processor': platform.processor(),
        'PythonVersion': platform.python_version(),
        'PythonImplementation': platform.python_implementation()
    }
    info['System'] = system_info
    
    cpu_info = {
        'PhysicalCores': psutil.cpu_count(logical=False),
        'LogicalCores': psutil.cpu_count(logical=True),
        'CPUFrequency': {
            'Min': psutil.cpu_freq().min if psutil.cpu_freq() else None,
            'Max': psutil.cpu_freq().max if psutil.cpu_freq() else None
        },
    }
    info['CPU'] = cpu_info
    
    memory = psutil.virtual_memory()
    swap = psutil.swap_memory()
    memory_info = {
        'TotalMemory_GB': round(memory.total / (1024**3), 2),
        'AvailableMemory_GB': round(memory.available / (1024**3), 2),
        'MemoryUsage_Percent': memory.percent,
        'SwapTotal_GB': round(swap.total / (1024**3), 2),
        'SwapUsed_GB': round(swap.used / (1024**3), 2),
        'SwapUsage_Percent': swap.percent
    }
    info['Memory'] = memory_info

    # deadly BUG, you import torch before forking the damn process !!!
    # cuda_info = {}
    # try:
    #     import torch
    #     cuda_available = torch.cuda.is_available()
    #     cuda_info['CUDA_Available'] = cuda_available
    #     if cuda_available:
    #         device_count = torch.cuda.device_count()
    #         cuda_info['GPU_Count'] = device_count
    #         current_device = torch.cuda.current_device()
    #         cuda_info['Current_Device'] = current_device
    #         cuda_info['Current_Device_Name'] = torch.cuda.get_device_name(current_device)
    # except Exception as e:
    #     cuda_info['Error'] = str(e)
    # info['CUDA'] = cuda_info

    network_info = {
        'Hostname': socket.gethostname(),
    }
    info['Network'] = network_info
    return info
    

def register_mx_info(logdir):
    info = get_mx_info()
    os.makedirs(logdir, exist_ok=True)
    with open(f'{logdir}/mx_info.json', 'w+') as f:
        json.dump(info, f, indent=2)
    return info