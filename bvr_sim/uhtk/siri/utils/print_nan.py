import numpy as np

def check_nan(traj_np):
    is_not_nan = np.zeros((len(traj_np),), dtype=int)
    for i in range(len(traj_np)):
        is_not_nan[i] = -np.any(np.isnan(traj_np[i]), axis=None).astype(int) + 1
    
    not_nan_ratio = (np.sum(is_not_nan, axis=0)/len(is_not_nan))
    assert not_nan_ratio == 1., f"not_nan_ratio={not_nan_ratio}"


def print_nan(traj_np):
    is_not_nan = np.zeros((len(traj_np),), dtype=int)
    for i in range(len(traj_np)):
        is_not_nan[i] = -np.any(np.isnan(traj_np[i]), axis=None).astype(int) + 1

    print(f"not NaN percent: {round(np.sum(is_not_nan, axis=0)/len(is_not_nan) * 100, 2)}%")